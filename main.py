import pandas as pd
import os
import uuid
import math 

# --- 1. MAPPING E CALCOLO LOGICO ---
def crea_modello_canonico(riga):
    # Mapping Genere
    sesso = str(riga.get('Sesso', 'UNK')).strip()
    genere_hl7 = 'M' if sesso == 'Male' else 'F' if sesso == 'Female' else 'UNK'

    # Estrazione Età e Anno di Nascita
    anno_attuale = 2026 
    try:
        eta = float(riga.get('Eta', 0))
        anno_nascita = anno_attuale - int(eta)
    except ValueError:
        eta = 0.0
        anno_nascita = 0000
    
    data_nascita_hl7 = f"{anno_nascita}0101"
    id_soggetto = str(riga.get('ID_Soggetto', 'ID_Mancante'))

    paziente = {
        "id": id_soggetto,
        "genere": genere_hl7,
        "data_nascita": data_nascita_hl7,
        "anno_nascita_visuale": str(anno_nascita)
    }

    # Estrazione sicura dei parametri clinici standard 
    try:
        altezza_in = float(riga.get('Altezza_in', 0.0))
        altezza_cm = round(altezza_in * 2.54, 1) if altezza_in > 0 else 0.0
        
        peso = float(riga.get('Peso_kg', 0.0))
        moca = float(riga.get('MoCA', 30))
        updrs = float(riga.get('UPDRS_3_TOT', 0))
        vel = float(riga.get('HurriedPace_Velocity_cm_sec', 173.2))
        lung_passo = float(riga.get('HurriedPace_StepLength_Mean', 0.0))
        
        hoehn_yahr = float(riga.get('Hoehn_Yahr', 0.0))
        anni_diagnosi = float(riga.get('Anni_Diagnosi', 0.0))
        
    except ValueError:
        altezza_cm, peso, moca, updrs, vel, lung_passo = 0.0, 0.0, 30.0, 0.0, 173.2, 0.0
        hoehn_yahr, anni_diagnosi = 0.0, 0.0

    # --- CALCOLO FENOTIPO CLINICO ---
    if moca >= 26 and updrs <= 6:
        fenotipo = "Sani Puri (Resilienti)"
    elif moca < 26 and updrs <= 6:
        fenotipo = "Vulnerabili Cognitivi"
    elif moca >= 26 and updrs > 6:
        fenotipo = "Vulnerabili Motori"
    else:
        fenotipo = "Vulnerabili Globali"

    # --- CALCOLO IVP ---
    moca_inv = (30.0 - moca) / (30.0 - 18.0) if moca >= 18 else 1.0
    vel_inv = (173.2 - vel) / (173.2 - 53.1) if vel <= 173.2 else 0.0
    
    moca_inv = max(0.0, min(1.0, moca_inv))
    vel_inv = max(0.0, min(1.0, vel_inv))

    eta_min, eta_max = 66.0, 91.0
    updrs_min, updrs_max = 0.0, 43.0

    eta_norm = (eta - eta_min) / (eta_max - eta_min)
    updrs_norm = (updrs - updrs_min) / (updrs_max - updrs_min)

    eta_norm = max(0.0, min(1.0, eta_norm))
    updrs_norm = max(0.0, min(1.0, updrs_norm))

    # Pesi per l'IVP (MoCA 41.4%, UPDRS 31.8%, Velocità 21.6%, Età 5.1%)
    ivp_calc = ((eta_norm * 0.051) + (moca_inv * 0.414) + (updrs_norm * 0.318) + (vel_inv * 0.216)) * 100
    ivp_score = round(ivp_calc, 1)

    # --- SOGLIE CORRETTE IVP ---
    if ivp_score < 25:
        livello_rischio = "Danno assente/lieve (<25)"
    elif 25 <= ivp_score < 50:
        livello_rischio = "Danno moderato (25-50)"
    elif 50 <= ivp_score < 75:
        livello_rischio = "Danno severo (50-75)"
    else:
        livello_rischio = "Danno alto (>75)"

    # --- CALCOLO MATEMATICO DELL'IRP TRAMITE FUNZIONE LOGISTICA ---
    try:
        # Ricostruzione della curva di regressione logistica del modello
        logit = (0.1805 * ivp_score) - 6.317
        irp_calc = 100 / (1 + math.exp(-logit))
        irp_score = round(irp_calc, 1)
    except Exception:
        irp_score = 0.0

    # --- SOGLIE CORRETTE CLASSE IRP ---
    if irp_score < 25:
        classe_irp = "Compenso/Stabile (<25%)"
    elif 25 <= irp_score < 50:
        classe_irp = "Allarme Precoce (25-50%)"
    elif 50 <= irp_score < 75:
        classe_irp = "Tipping Point (50-75%)"
    else:
        classe_irp = "Rottura Compenso (>75%)"

    # --- PARAMETRI CLINICI STANDARD (LOINC/SNOMED) ---
    # Nota: Manteniamo & nel Python, verrà convertito in &amp; al momento dell'export XML
    osservazioni_standard = [
        {"codice": "8302-2", "sistema": "2.16.840.1.113883.6.1", "label": "Altezza", "valore": altezza_cm, "tipo": "PQ", "unita": "cm"},
        {"codice": "29463-7", "sistema": "2.16.840.1.113883.6.1", "label": "Peso", "valore": peso, "tipo": "PQ", "unita": "kg"},
        {"codice": "75540-5", "sistema": "2.16.840.1.113883.6.1", "label": "Stadio di Hoehn & Yahr", "valore": hoehn_yahr, "tipo": "REAL", "unita": ""},
        {"codice": "85703-7", "sistema": "2.16.840.1.113883.6.1", "label": "Anni dalla Diagnosi", "valore": anni_diagnosi, "tipo": "PQ", "unita": "a"},
        {"codice": "72133-2", "sistema": "2.16.840.1.113883.6.1", "label": "Montreal Cognitive Assessment [MoCA]", "valore": moca, "tipo": "REAL", "unita": ""},
        {"codice": "77717-7", "sistema": "2.16.840.1.113883.6.1", "label": "MDS-UPDRS Part III (Motor)", "valore": updrs, "tipo": "REAL", "unita": ""},
        {"codice": "724237005", "sistema": "2.16.840.1.113883.6.96", "label": "Gait speed (observable entity)", "valore": vel, "tipo": "PQ", "unita": "cm/s"},
        {"codice": "250000008", "sistema": "2.16.840.1.113883.6.96", "label": "Step length (observable entity)", "valore": lung_passo, "tipo": "PQ", "unita": "cm"}
    ]

    # --- PARAMETRI PREDITTIVI LOCALI ---
    osservazioni_locali = [
        {"local_code": "IVP_SCORE", "label": "Indice Vulnerabilità Prodromica (IVP)", "valore": ivp_score, "tipo": "REAL"},
        {"local_code": "IVP_CLASS", "label": "Classe IVP (Livello di Danno)", "valore": livello_rischio, "tipo": "ST"},
        {"local_code": "IRP_SCORE", "label": "Indice di Rottura Compenso (IRP) %", "valore": irp_score, "tipo": "REAL"},
        {"local_code": "IRP_CLASS", "label": "Classe IRP (Stato di Compenso)", "valore": classe_irp, "tipo": "ST"},
        {"local_code": "PHENOTYPE", "label": "Fenotipo Clinico Prodromico", "valore": fenotipo, "tipo": "ST"}
    ]
    
    return {"paziente": paziente, "osservazioni_standard": osservazioni_standard, "osservazioni_locali": osservazioni_locali}

# --- 2. GENERATORE XML CDA R2 ---
def genera_xml(data):
    entries = ""
    righe_tabella = ""
    
    #  Generiamo i blocchi XML di Supporto
    xml_locali = ""
    oid_locale = "2.16.840.1.113883.2.9.2.80.4.99.1"
    for obs_loc in data['osservazioni_locali']:
        val = str(obs_loc['valore'])
        if val and val != 'nan' and val != 'N/D':
            # Escape sicuro per valori e per le etichette XML
            val_sicuro = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            label_sicuro = obs_loc['label'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            value_tag = f'<value xsi:type="REAL" value="{val_sicuro}"/>' if obs_loc['tipo'] == 'REAL' else f'<value xsi:type="ST">{val_sicuro}</value>'
            id_obs_loc = str(uuid.uuid4()).upper()

            xml_locali += f"""
                            <entryRelationship typeCode="SPRT">
                                <observation classCode="OBS" moodCode="EVN">
                                    <id root="2.16.840.1.113883.2.9.2.80.4.4" extension="{id_obs_loc}"/>
                                    <code code="{obs_loc['local_code']}" codeSystem="{oid_locale}" codeSystemName="Sistema Predittivo Parkinson" displayName="{label_sicuro}"/>
                                    <statusCode code="completed"/>
                                    <effectiveTime value="20260517110000+0200"/>
                                    {value_tag}
                                </observation>
                            </entryRelationship>"""

    #  Tabella Narrativa
    tutte_le_osservazioni = data['osservazioni_standard'] + data['osservazioni_locali']
    for obs in tutte_le_osservazioni:
        val = str(obs['valore'])
        if val and val != 'nan' and val != 'N/D':
            val_sicuro = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            label_sicuro = obs['label'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            unita_visiva = f" {obs.get('unita', '')}" if obs.get('unita') else ""
            righe_tabella += f"<tr><td><content styleCode=\"Bold\">{label_sicuro}</content></td><td>{val_sicuro}{unita_visiva}</td></tr>"

    #  Generiamo le entry cliniche standard principali
    for obs in data['osservazioni_standard']:
        val = str(obs['valore'])
        if val and val != 'nan' and val != 'N/D':
            val_sicuro = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            label_sicuro = obs['label'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            if obs['tipo'] == 'REAL':
                value_tag = f'<value xsi:type="REAL" value="{val_sicuro}"/>'
            elif obs['tipo'] == 'PQ':
                value_tag = f'<value xsi:type="PQ" value="{val_sicuro}" unit="{obs["unita"]}"/>'
            else:
                value_tag = f'<value xsi:type="ST">{val_sicuro}</value>'

            nidificazione = xml_locali if obs['codice'] == "77717-7" else ""
            id_obs_std = str(uuid.uuid4()).upper()
            
            entries += f"""
                    <entry>
                        <observation classCode="OBS" moodCode="EVN">
                            <templateId root="2.16.840.1.113883.2.9.10.1.4.3.1.1"/>
                            <id root="2.16.840.1.113883.2.9.2.80.4.4" extension="{id_obs_std}"/>
                            <code code="{obs['codice']}" codeSystem="{obs['sistema']}" displayName="{label_sicuro}"/>
                            <statusCode code="completed"/>
                            <effectiveTime value="20260517110000+0200"/>
                            {value_tag}{nidificazione}
                        </observation>
                    </entry>"""

    #  Layout Documento Completo
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:sdtc="urn:hl7-org:sdtc">
    <realmCode code="IT"/>
    <typeId root="2.16.840.1.113883.1.3" extension="POCD_HD000040"/>
    <templateId root="2.16.840.1.113883.2.9.10.1.9.1" extension="1.1"/>
    <id root="2.16.840.1.113883.2.9.2.80.4.4" extension="REF-2026-{data['paziente']['id']}-001"/>
    <code code="11488-4" codeSystem="2.16.840.1.113883.6.1" codeSystemName="LOINC" displayName="Referto di consulto"/>
    <title>Referto Screening Prodromico Parkinson - Soggetto {data['paziente']['id']}</title>
    <effectiveTime value="20260517110000+0200"/>
    <confidentialityCode code="N" codeSystem="2.16.840.1.113883.5.25" displayName="Normal"/>
    <languageCode code="it-IT"/>
    <setId root="2.16.840.1.113883.2.9.2.80.4.4" extension="SET-{data['paziente']['id']}-001"/>
    <versionNumber value="1"/>

    <recordTarget>
        <patientRole>
            <id root="2.16.840.1.113883.2.9.4.3.2" extension="RSSMRA53A01H501Z"/>
            <patient>
                <name>
                    <given>Paziente</given>
                    <family>{data['paziente']['id']}</family>
                </name>
                <administrativeGenderCode code="{data['paziente']['genere']}" codeSystem="2.16.840.1.113883.5.1" codeSystemName="HL7 AdministrativeGender"/>
                <birthTime value="{data['paziente']['data_nascita']}"/>
            </patient>
        </patientRole>
    </recordTarget>

    <author>
        <time value="20260517110000+0200"/>
        <assignedAuthor>
            <id root="2.16.840.1.113883.2.9.4.3.2" extension="BNCLGI70B12F205W"/>
            <telecom use="WP" value="tel:+390510000000"/>
            <assignedPerson>
                <name>
                    <prefix>Dott.</prefix>
                    <given>Luigi</given>
                    <family>Bianchi</family>
                </name>
            </assignedPerson>
            <representedOrganization>
                <id root="2.16.840.1.113883.2.9.4.1.2" extension="080101"/>
                <name>Azienda USL di Bologna - Centro Biomeccanica</name>
            </representedOrganization>
        </assignedAuthor>
    </author>

    <custodian>
        <assignedCustodian>
            <representedCustodianOrganization>
                <id root="2.16.840.1.113883.2.9.4.1.2" extension="080101"/>
                <name>Azienda USL di Bologna</name>
            </representedCustodianOrganization>
        </assignedCustodian>
    </custodian>

    <legalAuthenticator>
        <time value="20260517110000+0200"/>
        <signatureCode code="S"/>
        <assignedEntity>
            <id root="2.16.840.1.113883.2.9.4.3.2" extension="BNCLGI70B12F205W"/>
            <assignedPerson>
                <name>
                    <prefix>Dott.</prefix>
                    <given>Luigi</given>
                    <family>Bianchi</family>
                </name>
            </assignedPerson>
            <representedOrganization>
                <id root="2.16.840.1.113883.2.9.4.1.2" extension="080101"/>
                <name>Azienda USL di Bologna - Centro Biomeccanica</name>
            </representedOrganization>
        </assignedEntity>
    </legalAuthenticator>

    <componentOf>
        <encompassingEncounter>
            <effectiveTime value="20260517110000+0200"/>
            <location>
                <healthCareFacility>
                    <serviceProviderOrganization>
                        <id root="2.16.840.1.113883.2.9.4.1.2" extension="080101"/>
                        <name>Azienda USL di Bologna - Centro Biomeccanica</name>
                        <asOrganizationPartOf>
                            <id root="2.16.840.1.113883.2.9.4.1.1" extension="080101"/>
                        </asOrganizationPartOf>
                    </serviceProviderOrganization>
                </healthCareFacility>
            </location>
        </encompassingEncounter>
    </componentOf>

    <component>
        <structuredBody>
            
            <component>
                <section>
                    <code code="29299-5" codeSystem="2.16.840.1.113883.6.1" codeSystemName="LOINC" displayName="Motivo della visita"/>
                    <title>Quesito Diagnostico</title>
                    <text>
                        <paragraph>Sospetto clinico prodromico parkinsoniano in valutazione per inquadramento della vulnerabilità fenotipica.</paragraph>
                    </text>
                </section>
            </component>

            <component>
                <section>
                    <code code="62387-6" codeSystem="2.16.840.1.113883.6.1" codeSystemName="LOINC" displayName="Interventi clinici effettuati"/>
                    <title>Prestazioni</title>
                    <text>
                        <paragraph>Al fine di ottenere i dati per la refertazione odierna, sono state eseguite le seguenti procedure cliniche e valutazioni informatiche sul paziente:</paragraph>
                        <list listType="ordered">
                            <item>Somministrazione del test neuropsicologico Montreal Cognitive Assessment (MoCA).</item>
                            <item>Valutazione motoria tramite scala MDS-UPDRS Part III.</item>
                            <item>Analisi cinematica del cammino per la valutazione di parametri spazio-temporali.</item>
                            <item>Applicazione di algoritmo informatico predittivo per il calcolo della Vulnerabilità Parkinsoniana.</item>
                        </list>
                    </text>
                    <entry>
                        <act classCode="ACT" moodCode="EVN">
                            <id root="2.16.840.1.113883.2.9.2.80.4.4" extension="ACT-{data['paziente']['id']}"/>
                            <code code="81375008" codeSystem="2.16.840.1.113883.6.96" codeSystemName="SNOMED CT" displayName="Valutazione dell'andatura (Gait assessment)"/> 
                            <effectiveTime value="20260517110000+0200"/>
                        </act>
                    </entry>
                </section>
            </component>

            <component>
                <section>
                    <templateId root="2.16.840.1.113883.2.9.10.1.4.2.14" extension="1.1"/>
                    <code code="47045-0" codeSystem="2.16.840.1.113883.6.1" codeSystemName="LOINC" displayName="Referto di studio"/>
                    <title>Referto</title>
                    <text>
                        <table border="1" width="100%">
                            <tr><th>Parametro Analizzato</th><th>Risultato</th></tr>
                            <tr><td><content styleCode="Bold">ID Soggetto nel Dataset</content></td><td>{data['paziente']['id']}</td></tr>
                            <tr><td><content styleCode="Bold">Anno di Nascita (calcolato)</content></td><td>{data['paziente']['anno_nascita_visuale']}</td></tr>
                            {righe_tabella}
                        </table>
                        <br/>
                        <paragraph>
                            <caption>Nota Metodologica sul Modello Predittivo</caption>
                            La valutazione predittiva presentata in tabella è stata effettuata utilizzando un modello statistico di regressione logistica. Si precisa che tale modello è stato calibrato su un gruppo di studio ristretto composto da soli 36 pazienti. Il modello presenta una valutazione predittiva con una curva ROC avente un AUC di 0.972 e una sensibilità dello 0.88.
                        </paragraph>
                    </text>{entries}
                </section>
            </component>

        </structuredBody>
    </component>
</ClinicalDocument>"""
    return xml_content

# --- 3. FUNZIONE PRINCIPALE ---
def avvia_conversione():
    file_input = "data/dataset_pazienti.csv" 
    cartella_xml = "cda_xml"
    
    if not os.path.exists(file_input):
        print(f"Errore: Non trovo il file {file_input}")
        return

    os.makedirs(cartella_xml, exist_ok=True)
    df = pd.read_csv(file_input)

    for _, riga in df.iterrows():
        dati_puliti = crea_modello_canonico(riga)
        testo_xml = genera_xml(dati_puliti)
        
        id_paz = dati_puliti['paziente']['id']
        nome_file = f"{cartella_xml}/Referto_{id_paz}.xml"
        
        with open(nome_file, "w", encoding="utf-8") as f:
            f.write(testo_xml)
    
    print(f" Successo! Generati {len(df)} file XML in '{cartella_xml}/'")

if __name__ == "__main__":
    avvia_conversione()