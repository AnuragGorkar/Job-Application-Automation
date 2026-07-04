import json 

INPUT_FILE = "company_map_updated.json"

def main():
    with open(INPUT_FILE, "r") as f:
        company_map = json.load(f)
    
    for ats in company_map.keys():
        print(f"ATS: {ats}, total count: {len(company_map[ats])}")


if __name__ == "__main__":
    main()
