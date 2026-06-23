import json
from pathlib import Path

topo_dir = Path("../../01_Processed_Data/08_River_Network_Topology")

# Mapping rules based on the master station index
CANONICAL_CODES = {
    # Table 3.2 (natural gauges) — no leading zeros
    "A01": "A01", "A02": "A02", "A03": "A03", "A04": "A04", 
    "A05": "A05", "A06": "A06", "A06A": "A06A", "A07": "A07", "A08": "A08",
    "A001": "A01", "A002": "A02", "A003": "A03", "A004": "A04",
    "A005": "A05", "A006": "A06", "A007": "A07", "A008": "A08",
    "B01": "B01", "B02": "B02", "B001": "B01", "B002": "B02",
    "C01": "C01", "C001": "C01",
    "D01": "D01", "D001": "D01",
    "E01": "E01", "E02": "E02", "E03": "E03", "E04": "E04", 
    "E05": "E05", "E06": "E06", "E06A": "E06A", "E07": "E07", 
    "E09": "E09", "E11": "E11", "E12": "E12", "E13": "E13", 
    "E14": "E14", "E15": "E15", "E16": "E16", "E17": "E17", 
    "E18": "E18", "E19": "E19", "E20": "E20", "E21": "E21", 
    "E22": "E22", "E23": "E23",
    "E001": "E01", "E002": "E02", "E003": "E03", "E004": "E04", 
    "E005": "E05", "E006": "E06", "E007": "E07",
    
    # Table 3.3 (diversion canal gauges) — WITH leading zeros, kept distinct
    "E008A": "E008A", "E008a": "E008A",
    "E008B": "E008B", "E008b": "E008B",
    "E008C": "E008C", "E008c": "E008C",
    "E013": "E013",  # Distinct from E13
    "E014": "E014",  # Distinct from E14
    "E015A": "E015A", "E015a": "E015A",
    "E020": "E020",  # Distinct from E20
    
    # Other common natural basins
    "F01": "F01", "F001": "F01",
    "G09": "G09", "G009": "G09",
    "H02": "H02", "H002": "H02",
    "J01": "J01", "J001": "J01",
    "L01": "L01", "L001": "L01",
    "M01": "M01", "M001": "M01",
    "N03": "N03", "N003": "N03",
    "P01": "P01", "P001": "P01",
    "R01": "R01", "R001": "R01",
    "W01": "W01", "W001": "W01", "W02": "W02", "W03": "W03", "W04": "W04",
    "Y01": "Y01", "Y001": "Y01", "Y02": "Y02", "Y02A": "Y02A", "Y02a": "Y02A",
}

def normalize_code(code):
    """Normalize station code: uppercase only, NEVER strip leading zeros blindly."""
    if not code:
        return code
    code = code.upper().strip()
    return CANONICAL_CODES.get(code, code)  # return as-is if not in mapping

for json_file in topo_dir.glob("*.json"):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    modified = False
    
    # Depending on the JSON structure
    if "diagrams" in data:
        for diag in data["diagrams"]:
            if "stations" in diag:
                new_stations = []
                for st in diag["stations"]:
                    old_code = st.get("code")
                    old_conn = st.get("connected_to")
                    new_code = normalize_code(old_code)
                    new_conn = normalize_code(old_conn)
                    
                    # Drop phantom nodes
                    if new_code in ["A09", "A010", "A011", "E009", "E010"]:
                        modified = True
                        continue
                        
                    if old_code != new_code:
                        st["code"] = new_code
                        modified = True
                    if old_conn != new_conn:
                        st["connected_to"] = new_conn
                        modified = True
                        
                    # Fix Cycles & Bad Rules
                    if new_code in ["A07", "A08"] and new_conn in ["A07", "A08"]:
                        st["connected_to"] = None
                        modified = True
                    if new_code == "E04" and new_conn == "E04":
                        st["connected_to"] = None
                        modified = True
                    if new_code == "E13" and new_conn == "E013":
                        st["connected_to"] = "SEA"
                        modified = True
                        
                    new_stations.append(st)
                diag["stations"] = new_stations
                    
            if "diversions" in diag:
                for div in diag["diversions"]:
                    old_code = div.get("code")
                    if old_code:
                        new_code = normalize_code(old_code)
                        if old_code != new_code:
                            div["code"] = new_code
                            modified = True
                    old_conn = div.get("connected_to")
                    if old_conn:
                        new_conn = normalize_code(old_conn)
                        if old_conn != new_conn:
                            div["connected_to"] = new_conn
                            modified = True
                            
            if "infrastructure" in diag:
                for inf in diag["infrastructure"]:
                    old_conn = inf.get("connected_to")
                    if old_conn:
                        new_conn = normalize_code(old_conn)
                        if old_conn != new_conn:
                            inf["connected_to"] = new_conn
                            modified = True
    
    # Some older files might have "records" (e.g. clean_river_network)
    if "records" in data:
        new_records = []
        for rec in data["records"]:
            old_code = rec.get("station_code") or rec.get("code")
            old_conn = rec.get("connected_to")
            new_code = normalize_code(old_code)
            new_conn = normalize_code(old_conn)
            
            # Drop phantom nodes
            if new_code in ["A09", "A010", "A011", "E009", "E010"]:
                modified = True
                continue
                
            if old_code != new_code:
                if "station_code" in rec: rec["station_code"] = new_code
                if "code" in rec: rec["code"] = new_code
                modified = True
            if old_conn != new_conn:
                rec["connected_to"] = new_conn
                modified = True
                
            # Fix Cycles & Bad Rules
            if new_code in ["A07", "A08"] and new_conn in ["A07", "A08"]:
                rec["connected_to"] = None
                modified = True
            if new_code == "E04" and new_conn == "E04":
                rec["connected_to"] = None
                modified = True
            if new_code == "E13" and new_conn == "E013":
                rec["connected_to"] = "SEA"
                modified = True
                
            new_records.append(rec)
        data["records"] = new_records
                
    if modified:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Updated {json_file.name}")
