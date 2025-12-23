from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path
import os

# 加载同目录 .env
load_dotenv(Path(__file__).with_name(".env"))

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USERNAME")
pwd  = os.getenv("NEO4J_PASSWORD")
db   = os.getenv("NEO4J_DATABASE", "neo4j")

driver = GraphDatabase.driver(uri, auth=(user, pwd))
driver.verify_connectivity()  # 验证连接

with driver.session(database=db) as s:
    rec = s.run("RETURN 1 AS ok").single()
    print("ok =", rec["ok"])

driver.close()