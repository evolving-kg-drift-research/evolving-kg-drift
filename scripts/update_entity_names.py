import pandas as pd
from neo4j import GraphDatabase
from src.kg_pipeline.hashing import sha256_text

def update_entity_names():
    print("Reading extracted claims...")
    df_claims = pd.read_parquet("runs/production_v3/tables/extracted_claims.parquet")
    
    mapping = {}
    for _, row in df_claims.iterrows():
        s_m = str(row["subject_mention"]).strip()
        o_m = str(row["object_mention"]).strip()
        if s_m and s_m != "None":
            eid = f"ent_{sha256_text(s_m.lower())[:8]}"
            mapping[eid] = s_m
        if o_m and o_m != "None":
            eid = f"ent_{sha256_text(o_m.lower())[:8]}"
            mapping[eid] = o_m

    print(f"Mapped {len(mapping)} entity IDs to real human-readable names.")
    
    driver = GraphDatabase.driver("bolt://127.0.0.1:7687")
    with driver.session() as session:
        batch = [{"id": k, "name": v} for k, v in mapping.items()]
        query = """
        UNWIND $batch AS row
        MATCH (e:Entity {id: row.id})
        SET e.name = row.name
        """
        session.run(query, {"batch": batch})
        
        # Verify
        c = session.run("MATCH (e:Entity) WHERE e.name IS NOT NULL RETURN count(e) AS c").single()["c"]
        print(f"SUCCESS: Cap nhat ten that cho {c} / 1389 Entity nodes trong Neo4j!")

if __name__ == "__main__":
    update_entity_names()
