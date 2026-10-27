import pyarrow.parquet as pq
from neo4j import GraphDatabase

def check_parity():
    driver = GraphDatabase.driver("bolt://127.0.0.1:7687")
    with driver.session() as s:
        print("========================================================================")
        print("  SNAPSHOT ID | NEO4J EDGES | CANONICAL PARQUET EDGES | PARITY STATUS")
        print("========================================================================")
        all_pass = True
        for i in range(1, 11):
            sid = f"T{i:02d}"
            query = f"MATCH ()-[r]->() WHERE '{sid}' IN r.snapshots RETURN count(r) AS c"
            res = s.run(query).single()["c"]
            pq_tbl = pq.read_table(f"runs/production_v3/snapshots/snapshot_{sid}_canonical.parquet")
            pq_count = pq_tbl.num_rows
            match = (res == pq_count)
            if not match:
                all_pass = False
            status = "PASS" if match else "FAIL"
            print(f"     {sid}      |    {res:5d}    |          {pq_count:5d}         |     {status}")
        print("========================================================================")
        print("CANONICAL PARQUET <-> NEO4J DATABASE READ-BACK PARITY:", "ALL PASS" if all_pass else "FAIL")
        
        # In tổng thể Node Entity
        n_neo = s.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
        print(f"Total Unique Entity Nodes in Neo4j: {n_neo} (Parquet T10: 1389) -> {'PASS' if n_neo == 1389 else 'FAIL'}")

if __name__ == "__main__":
    check_parity()
