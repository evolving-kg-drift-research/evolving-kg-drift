import sys
import pandas as pd
from neo4j import GraphDatabase

def main():
    print("Ket noi toi Neo4j (bolt://127.0.0.1:7687)...")
    driver = GraphDatabase.driver("bolt://127.0.0.1:7687")
    
    with driver.session() as session:
        print("1. Xoa du lieu cu...")
        session.run("MATCH (n) DETACH DELETE n")
        
        print("2. Tao constraint cho Entity id...")
        session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
        
        print("3. Tong hop danh sach Entity tu T01 den T10...")
        node_snapshots = {}
        for snap_num in range(1, 11):
            snap_id = f"T{snap_num:02d}"
            csv_path = f"runs/production_v3/neo4j_materialization/{snap_id}/nodes.csv"
            df_nodes = pd.read_csv(csv_path)
            for eid in df_nodes["entity_id:ID"]:
                if eid not in node_snapshots:
                    node_snapshots[eid] = set()
                node_snapshots[eid].add(snap_id)

        nodes_batch = [{"id": eid, "snapshots": sorted(list(snaps))} for eid, snaps in node_snapshots.items()]
        
        query_nodes = """
        UNWIND $batch AS item
        MERGE (e:Entity {id: item.id})
        SET e.snapshots = item.snapshots, e.first_seen = item.snapshots[0]
        """
        session.run(query_nodes, {"batch": nodes_batch})
        print(f"   -> Da nap {len(nodes_batch)} Entity nodes.")

        print("4. Nap cac quan he (Relationships) tu T01 den T10...")
        for snap_num in range(1, 11):
            snap_id = f"T{snap_num:02d}"
            csv_path = f"runs/production_v3/neo4j_materialization/{snap_id}/relationships.csv"
            df_rels = pd.read_csv(csv_path)
            
            for rel_type, group in df_rels.groupby(":TYPE"):
                safe_type = str(rel_type).upper().replace("-", "_").replace(" ", "_")
                batch = []
                for _, r in group.iterrows():
                    batch.append({
                        "start_id": str(r[":START_ID"]),
                        "end_id": str(r[":END_ID"]),
                        "fact_version_id": str(r["fact_version_id"]),
                        "logical_fact_id": str(r["logical_fact_id"]),
                        "valid_from": str(r["valid_from"]),
                        "valid_to": str(r["valid_to"]) if pd.notna(r["valid_to"]) else "",
                        "evidence_observed_at": str(r["evidence_observed_at"]),
                        "source_id": str(r["source_id"]),
                        "snapshot": snap_id
                    })
                
                query_rels = f"""
                UNWIND $batch AS r
                MATCH (src:Entity {{id: r.start_id}})
                MATCH (dst:Entity {{id: r.end_id}})
                MERGE (src)-[rel:{safe_type} {{logical_fact_id: r.logical_fact_id}}]->(dst)
                ON CREATE SET 
                    rel.fact_version_id = r.fact_version_id,
                    rel.valid_from = r.valid_from,
                    rel.valid_to = r.valid_to,
                    rel.evidence_observed_at = r.evidence_observed_at,
                    rel.source_id = r.source_id,
                    rel.snapshots = [r.snapshot]
                ON MATCH SET
                    rel.snapshots = CASE WHEN r.snapshot IN rel.snapshots THEN rel.snapshots ELSE rel.snapshots + r.snapshot END
                """
                session.run(query_rels, {"batch": batch})
            print(f"   -> Snapshot {snap_id} da nap ({len(df_rels)} edges).")

        n_count = session.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
        r_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        
        # Thong ke quan he theo loai
        rel_types = session.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY c DESC").data()
        
        print("\n==========================================")
        print("🎉 NAP DU LIEU VAO NEO4J HOAN TAT!")
        print(f"Tong so Thuc the (Entity nodes): {n_count}")
        print(f"Tong so Cạnh quan he (Relationships): {r_count}")
        print("Phan bo theo loai quan he:")
        for rt in rel_types:
            print(f"  - {rt['t']}: {rt['c']}")
        print("==========================================")

if __name__ == "__main__":
    main()
