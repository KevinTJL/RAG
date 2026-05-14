# app/graph_store.py
import json
from pathlib import Path
import networkx as nx
from app.config import settings

class GraphStore:
    def __init__(self):
        self.graph = nx.DiGraph()
        # 将图谱数据保存在和 chroma 同级的 db 目录下
        self.graph_path = settings.project_root / "db" / "graph.json"
        
    def load(self):
        """从本地加载已被提取保存的图数据"""
        if self.graph_path.exists():
            try:
                with open(self.graph_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception as e:
                print(f"Failed to load graph: {e}")
                self.graph = nx.DiGraph()

    def save(self):
        """持久化保存当下的图"""
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.graph)
        with open(self.graph_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear(self):
        self.graph.clear()
        self.save()

    def add_triplet(self, head: str, relation: str, tail: str, source: str = ""):
        """增加一个事实三元组：头实体 -关系-> 尾实体"""
        if not head or not tail or not relation:
            return
            
        # 简单清洗实体名称里的无用标点
        head = head.strip(''' "'`\t\n''')
        tail = tail.strip(''' "'`\t\n''')
        relation = relation.strip()

        # 添加节点和边
        self.graph.add_node(head)
        self.graph.add_node(tail)
        self.graph.add_edge(head, tail, relation=relation, source=source)