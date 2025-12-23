from neo4j import GraphDatabase
import os
from pathlib import Path
from dotenv import load_dotenv

# 1) 加载 .env（同目录优先）
env_path = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=env_path if env_path.exists() else None)

# 2) 读取配置并做最小校验
URI = os.getenv("NEO4J_URI")
USERNAME = os.getenv("NEO4J_USERNAME")
PASSWORD = os.getenv("NEO4J_PASSWORD")

def _mask(v: str | None) -> str:
    if not v:
        return "<not set>"
    return "<set>" if len(v) < 6 else f"{v[:2]}***{v[-2:]}"

print(f"NEO4J_URI: {URI or '<not set>'}")
print(f"NEO4J_USERNAME: {USERNAME or '<not set>'}")
print(f"NEO4J_PASSWORD: {_mask(PASSWORD)}")

if not (URI and USERNAME and PASSWORD):
    print("❌ 配置不完整：请在 .env 中设置 NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD。")
    print("示例：\nNEO4J_URI=neo4j+s://<your>.databases.neo4j.io\nNEO4J_USERNAME=neo4j\nNEO4J_PASSWORD=<password>\n或本地：\nNEO4J_URI=bolt://localhost:7687")
    raise SystemExit(1)

# 3) 使用 with 管理 driver；异常自然抛出，逻辑更清晰
with GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD)) as driver:
    # (a) 连接验证
    driver.verify_connectivity()
    print("✅ 连接正常：已成功验证 Neo4j 可达性。")

    # (b) 使用 execute_query 创建数据
    print("▶ 创建示例数据（Alice -> David）...")
    summary = driver.execute_query(
        """
        CREATE (a:Person {name: $name})
        CREATE (b:Person {name: $friendName})
        CREATE (a)-[:KNOWS]->(b)
        """,
        name="Alice",
        friendName="David",
        database_="neo4j",
    ).summary
    print(
        "Created {nodes_created} nodes, {relationships_created} relationships in {time} ms.".format(
            nodes_created=summary.counters.nodes_created,
            relationships_created=summary.counters.relationships_created,
            time=summary.result_available_after,
        )
    )


    # (c) 使用 execute_query 查询数据
    print("▶ 查询所有有好友的 Person 名字...")
    records, summary, keys = driver.execute_query(
        """
        MATCH (p:Person)-[:KNOWS]->(:Person)
        RETURN p.name AS name
        """,
        database_="neo4j",
    )
    for record in records:
        print(record.data())
    print(
        "The query `{query}` returned {records_count} records in {time} ms.".format(
            query=summary.query,
            records_count=len(records),
            time=summary.result_available_after,
        )
    )

    # (d) 使用 with 管理 Session（更简洁，无 try/finally）
    print("▶ 演示手动 Session 用法...")
    with driver.session(database="neo4j") as session:
        res = session.run("RETURN 'ok' AS status").single()
        print("Session run status:", res["status"])
    print("Session 已关闭，Driver 也会在 with 结束后关闭。")