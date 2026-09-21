# ADR 0001 · 后端技术栈选型

- 状态：已接受（待 M0 语义 PoC 验证后最终确认）
- 日期：2026-09-21

## 背景

知识中台需要三类后端能力：常规 Web 服务、元数据库持久化、**真实语义执行**（RDF 解析/序列化、SHACL 校验、OWL 推理）。第三类是硬约束——demo 阶段的演示式校验不能延续到正式版。

## 决策

**Python 3.12 + FastAPI**，语义能力封装为可替换适配器 `app/semantics/`：

| 能力                       | 组件                                   | 许可       |
| -------------------------- | -------------------------------------- | ---------- |
| Web 框架                   | FastAPI + Pydantic v2                  | MIT        |
| ORM / 迁移                 | SQLAlchemy 2.0 + Alembic               | MIT        |
| RDF 解析 / 序列化 / SPARQL | rdflib                                 | BSD-3      |
| SHACL 校验（真实报告）     | pySHACL                                | Apache-2.0 |
| OWL 推理最小集             | owlrl                                  | BSD-3      |
| OWL-DL 一致性（可选）      | Apache Jena + HermiT（Docker sidecar） | Apache-2.0 |

## 备选与放弃理由

- **Java + Spring Boot + Apache Jena**：语义能力最完整，但迭代速度、前后端一体的开发效率、开源贡献门槛均劣于 Python 方案。
- **Node / NestJS**：JS 侧没有成熟稳定的 SHACL 实现与 OWL 推理器，H-04 会退化为自研，风险最高。
- **自建语义引擎**：不可接受，SHACL 规范细节足以拖垮主流程排期。

## 代价与缓解

- 完整 OWL-DL 一致性（校验项 A08）在内置栈下只能做到 RDFS/OWL 最小集，A08 如实标注"未执行"。
- 缓解：`app/semantics/` 定义 `parse / serialize / validate / reason` 接口，提供 `RdflibBackend` 与可选的 `JenaRemoteBackend`，替换实现不动业务代码。
- 硬边界：出具"符合 GB/T 48000.3—2026"结论前，必须接入真实推理器并跑通 A08。
