-- samples/seed.sql
-- 知识中台 M2 样例库：建表 + 灌数脚本（只读，可重放）
-- 脱敏：域名 example.org，信用代码 91310000DEMAxxxxxx 形式，虚构人名
-- 三类关系结构：
--   1. 外键          hr_employee.enterprise_id -> enterprise.id
--   2. 中间表        ct_contract_project(contract_id, project_id)  仅两列外键
--   3. 带属性关联表  pm_project_member（含 project_id=7001+member_id=8001 两条参与记录，
--                     role 分别为「项目经理」「技术负责人」，验证带属性关系不被三元组去重）
-- 五类经营知识场景（部门层级/股权架构/人物关系/客商/合同）覆盖：
--   自引用      org_department.parent_id（四层两棵树 + 一条孤儿 99 -> 9999，供隔离验证）
--   多态股东    eq_shareholder.shareholder_type ∈ {PERSON, ENTERPRISE}，人/企二选一
--   间接持股    eq_equity_holding 三层链 + 交叉 + 环路（1002 <-> 1007）+ 合计 160%/105% 异常
--   人物关系    person_relation（REPORTS_TO/COLLEAGUE/RELATIVE）+ 组织高管
--   客商双角色  crm_customer / crm_supplier 共享信用代码 91310000DEMA000006
--   合同签约方  ct_contract_party（PARTY_A/PARTY_B/PARTY_C）+ 补充协议 parent_contract_id

PRAGMA foreign_keys = ON;

-- 幂等：重放前按依赖逆序清表
DROP TABLE IF EXISTS crm_trade_transaction;
DROP TABLE IF EXISTS crm_supplier;
DROP TABLE IF EXISTS crm_customer;
DROP TABLE IF EXISTS eq_equity_holding;
DROP TABLE IF EXISTS eq_shareholder;
DROP TABLE IF EXISTS person_relation;
DROP TABLE IF EXISTS org_executive_role;
DROP TABLE IF EXISTS org_employment;
DROP TABLE IF EXISTS org_position;
DROP TABLE IF EXISTS org_department;
DROP TABLE IF EXISTS ct_contract_party;
DROP TABLE IF EXISTS pm_project_member;
DROP TABLE IF EXISTS ct_contract_project;
DROP TABLE IF EXISTS pm_project;
DROP TABLE IF EXISTS ct_contract;
DROP TABLE IF EXISTS hr_employee;
DROP TABLE IF EXISTS enterprise;

-- 1. 企业
CREATE TABLE enterprise (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    credit_code  TEXT NOT NULL UNIQUE,
    website      TEXT NOT NULL,
    founded_date TEXT NOT NULL
);

-- 2. 员工（外键 -> enterprise.id）  ← 外键关系
CREATE TABLE hr_employee (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    enterprise_id INTEGER NOT NULL,
    email         TEXT NOT NULL,
    hire_date     TEXT NOT NULL,
    position      TEXT NOT NULL,
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

-- 3. 合同（经办人 + 补充协议自引用）
CREATE TABLE ct_contract (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,
    title               TEXT NOT NULL,
    amount              REAL NOT NULL,
    sign_date           TEXT NOT NULL,
    handler_employee_id INTEGER,
    parent_contract_id  INTEGER REFERENCES ct_contract(id)
);

-- 4. 项目
CREATE TABLE pm_project (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    code       TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date   TEXT
);

-- 5. 合同-项目 中间表（仅两列外键 + 复合主键）  ← 中间表
CREATE TABLE ct_contract_project (
    contract_id INTEGER NOT NULL,
    project_id  INTEGER NOT NULL,
    PRIMARY KEY (contract_id, project_id),
    FOREIGN KEY (contract_id) REFERENCES ct_contract(id),
    FOREIGN KEY (project_id)  REFERENCES pm_project(id)
);

-- 5b. 合同签约方（带角色关联表）  ← 带角色关联
CREATE TABLE ct_contract_party (
    id            INTEGER PRIMARY KEY,
    contract_id   INTEGER NOT NULL,
    enterprise_id INTEGER NOT NULL,
    party_role    TEXT NOT NULL CHECK (party_role IN ('PARTY_A', 'PARTY_B', 'PARTY_C')),
    UNIQUE (contract_id, enterprise_id, party_role),
    FOREIGN KEY (contract_id)   REFERENCES ct_contract(id),
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

-- 6. 项目成员 带属性关联表  ← 带属性关联表
CREATE TABLE pm_project_member (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    member_id  INTEGER NOT NULL,
    role       TEXT NOT NULL,
    join_date  TEXT NOT NULL,
    leave_date TEXT,
    FOREIGN KEY (project_id) REFERENCES pm_project(id),
    FOREIGN KEY (member_id)  REFERENCES hr_employee(id)
);

-- ===== 灌数 =====

INSERT INTO enterprise (id, name, credit_code, website, founded_date) VALUES
    (1001, '示范科技有限公司', '91310000DEMA000001', 'https://co1001.example.org', '2001-03-15'),
    (1002, '样例数据科技',    '91310000DEMA000002', 'https://co1002.example.org', '2003-06-20'),
    (1003, '演示软件股份',    '91310000DEMA000003', 'https://co1003.example.org', '2005-09-10'),
    (1004, '虚构智能科技',    '91310000DEMA000004', 'https://co1004.example.org', '2007-11-05'),
    (1005, '测试云服务',      '91310000DEMA000005', 'https://co1005.example.org', '2009-04-18'),
    (1006, '示例数据工程',    '91310000DEMA000006', 'https://co1006.example.org', '2010-12-01'),
    (1007, '范例信息技术',    '91310000DEMA000007', 'https://co1007.example.org', '2012-03-22'),
    (1008, '样例网络科技',    '91310000DEMA000008', 'https://co1008.example.org', '2013-07-30'),
    (1009, '示范数字科技',    '91310000DEMA000009', 'https://co1009.example.org', '2015-02-14'),
    (1010, '虚构信息系统',    '91310000DEMA000010', 'https://co1010.example.org', '2016-08-09'),
    (1011, '示例人工智能',    '91310000DEMA000011', 'https://co1011.example.org', '2018-05-25'),
    (1012, '样例平台服务',    '91310000DEMA000012', 'https://co1012.example.org', '2020-10-11');

INSERT INTO hr_employee (id, name, enterprise_id, email, hire_date, position) VALUES
    (8001, '陈建国', 1001, 'emp8001@example.org', '2018-03-01', '工程师'),
    (8002, '林晓东', 1001, 'emp8002@example.org', '2019-06-15', '高级工程师'),
    (8003, '王丽华', 1002, 'emp8003@example.org', '2017-09-01', '架构师'),
    (8004, '李明',   1002, 'emp8004@example.org', '2018-12-01', '项目经理'),
    (8005, '张伟',   1003, 'emp8005@example.org', '2020-03-10', '测试工程师'),
    (8006, '刘洋',   1003, 'emp8006@example.org', '2021-04-05', '工程师'),
    (8007, '周敏',   1004, 'emp8007@example.org', '2019-01-20', '技术负责人'),
    (8008, '吴芳',   1004, 'emp8008@example.org', '2020-07-01', '高级工程师'),
    (8009, '郑磊',   1005, 'emp8009@example.org', '2021-02-15', '工程师'),
    (8010, '孙强',   1005, 'emp8010@example.org', '2022-03-01', '测试工程师'),
    (8011, '马涛',   1006, 'emp8011@example.org', '2018-05-20', '架构师'),
    (8012, '朱琳',   1006, 'emp8012@example.org', '2019-10-10', '项目经理'),
    (8013, '胡静',   1007, 'emp8013@example.org', '2020-11-01', '工程师'),
    (8014, '郭峰',   1007, 'emp8014@example.org', '2021-06-15', '高级工程师'),
    (8015, '何婷',   1008, 'emp8015@example.org', '2022-01-05', '测试工程师'),
    (8016, '高磊',   1008, 'emp8016@example.org', '2022-09-01', '工程师'),
    (8017, '罗宇',   1009, 'emp8017@example.org', '2019-04-10', '技术负责人'),
    (8018, '梁燕',   1009, 'emp8018@example.org', '2020-08-20', '高级工程师'),
    (8019, '宋杰',   1010, 'emp8019@example.org', '2021-12-01', '工程师'),
    (8020, '谢敏',   1010, 'emp8020@example.org', '2022-05-15', '测试工程师'),
    (8021, '韩雪',   1011, 'emp8021@example.org', '2018-11-01', '架构师'),
    (8022, '唐峰',   1011, 'emp8022@example.org', '2020-02-10', '项目经理'),
    (8023, '冯静',   1012, 'emp8023@example.org', '2021-07-01', '工程师'),
    (8024, '董磊',   1012, 'emp8024@example.org', '2022-04-15', '高级工程师'),
    (8025, '程曦',   1001, 'emp8025@example.org', '2023-03-01', '架构师');

INSERT INTO ct_contract (id, code, title, amount, sign_date, handler_employee_id, parent_contract_id) VALUES
    (6001, 'HT-2024-0001', '示范平台建设服务合同', 1280000.00, '2024-01-10', 8002, NULL),
    (6002, 'HT-2024-0002', '数据治理咨询合同',     560000.00, '2024-02-15', 8004, NULL),
    (6003, 'HT-2024-0003', '系统集成实施合同',     2100000.00, '2024-01-20', 8007, NULL),
    (6004, 'HT-2024-0004', '运维支持服务合同',     680000.00, '2024-03-01', 8004, NULL),
    (6005, 'HT-2024-0005', '数据中台开发合同',     3500000.00, '2024-03-15', 8012, NULL),
    (6006, 'HT-2024-0006', '知识图谱建设合同',     980000.00, '2024-04-01', 8012, NULL),
    (6007, 'HT-2024-0007', '前端界面定制合同',     760000.00, '2024-04-20', 8015, NULL),
    (6008, 'HT-2024-0008', '接口对接开发合同',     450000.00, '2024-05-10', 8015, NULL),
    (6009, 'HT-2024-0009', '数据迁移服务合同',     890000.00, '2024-05-25', 8019, NULL),
    (6010, 'HT-2024-0010', '测试评估服务合同',     320000.00, '2024-06-05', 8019, NULL),
    (6011, 'HT-2024-0011', '架构设计咨询合同',     540000.00, '2024-06-20', 8022, NULL),
    (6012, 'HT-2024-0012', '安全保障服务合同',     410000.00, '2024-07-01', 8022, NULL),
    (6013, 'HT-2024-0013', '培训实施服务合同',     150000.00, '2024-07-15', 8023, NULL),
    (6014, 'HT-2024-0014', '运维二期合同',         720000.00, '2024-08-01', 8004, 6004),
    (6015, 'HT-2024-0015', '扩展模块开发合同',     630000.00, '2024-08-20', 8012, 6005);

INSERT INTO pm_project (id, name, code, start_date, end_date) VALUES
    (7001, '示范知识中台',   'PRJ-2024-0001', '2024-01-01', NULL),
    (7002, '数据治理平台',   'PRJ-2024-0002', '2024-02-01', NULL),
    (7003, '系统集成项目',   'PRJ-2024-0003', '2024-01-01', '2024-09-30'),
    (7004, '运维支持项目',   'PRJ-2024-0004', '2024-03-01', NULL),
    (7005, '数据中台二期',   'PRJ-2024-0005', '2024-04-01', NULL),
    (7006, '知识图谱项目',   'PRJ-2024-0006', '2024-05-01', NULL),
    (7007, '前端定制项目',   'PRJ-2024-0007', '2024-06-01', NULL),
    (7008, '接口对接项目',   'PRJ-2024-0008', '2024-06-15', NULL),
    (7009, '数据迁移项目',   'PRJ-2024-0009', '2024-07-01', NULL),
    (7010, '测试评估项目',   'PRJ-2024-0010', '2024-07-15', NULL),
    (7011, '架构设计项目',   'PRJ-2024-0011', '2024-08-01', NULL),
    (7012, '安全保障项目',   'PRJ-2024-0012', '2024-08-15', NULL);

-- 中间表：合同与项目多对多
INSERT INTO ct_contract_project (contract_id, project_id) VALUES
    (6001, 7001), (6001, 7002),
    (6002, 7001), (6002, 7003),
    (6003, 7002), (6003, 7004),
    (6004, 7003), (6004, 7005),
    (6005, 7004), (6005, 7006),
    (6006, 7005), (6006, 7007),
    (6007, 7006), (6007, 7008),
    (6008, 7007), (6008, 7009),
    (6009, 7008), (6009, 7010);

-- 带属性关联表：项目成员
-- 注意前两行：project_id=7001 + member_id=8001 出现两次（项目经理 / 技术负责人）
INSERT INTO pm_project_member (id, project_id, member_id, role, join_date, leave_date) VALUES
    (1, 7001, 8001, '项目经理',    '2024-01-15', NULL),
    (2, 7001, 8001, '技术负责人',  '2024-02-01', NULL),
    (3, 7001, 8002, '开发工程师',  '2024-01-20', NULL),
    (4, 7001, 8005, '测试工程师',  '2024-02-10', NULL),
    (5, 7002, 8003, '项目经理',    '2024-03-01', NULL),
    (6, 7002, 8006, '开发工程师',  '2024-03-05', NULL),
    (7, 7002, 8010, '测试工程师',  '2024-03-10', NULL),
    (8, 7003, 8004, '项目经理',    '2024-01-10', '2024-08-31'),
    (9, 7003, 8007, '技术负责人',  '2024-01-15', NULL),
    (10, 7003, 8009, '开发工程师', '2024-02-01', NULL),
    (11, 7004, 8008, '项目经理',   '2024-04-01', NULL),
    (12, 7004, 8011, '架构师',     '2024-04-05', NULL),
    (13, 7005, 8012, '项目经理',   '2024-05-01', NULL),
    (14, 7005, 8015, '测试工程师', '2024-05-10', NULL),
    (15, 7006, 8016, '开发工程师', '2024-06-01', NULL),
    (16, 7006, 8017, '技术负责人', '2024-06-05', NULL),
    (17, 7007, 8020, '测试工程师', '2024-07-01', NULL),
    (18, 7008, 8021, '架构师',     '2024-07-05', NULL),
    (19, 7009, 8022, '项目经理',   '2024-08-01', NULL),
    (20, 7010, 8025, '架构师',     '2024-08-10', NULL);

-- ===== 五类经营知识场景 =====

-- 场景一：部门层级（自引用 + 四层两棵树 + 孤儿 99）
CREATE TABLE org_department (
    id            INTEGER PRIMARY KEY,
    enterprise_id INTEGER NOT NULL,
    parent_id     INTEGER REFERENCES org_department(id),
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

CREATE TABLE org_position (
    id   INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

-- 任职：员工 x 部门 x 岗位，带汇报上级与起止日期
CREATE TABLE org_employment (
    id                  INTEGER PRIMARY KEY,
    employee_id         INTEGER NOT NULL,
    department_id       INTEGER NOT NULL,
    position_id         INTEGER NOT NULL,
    manager_employee_id INTEGER,
    start_date          TEXT NOT NULL,
    end_date            TEXT,
    is_primary          INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    FOREIGN KEY (employee_id)         REFERENCES hr_employee(id),
    FOREIGN KEY (department_id)       REFERENCES org_department(id),
    FOREIGN KEY (position_id)         REFERENCES org_position(id),
    FOREIGN KEY (manager_employee_id) REFERENCES hr_employee(id)
);

-- 场景二：股权架构（PERSON/ENTERPRISE 多态股东）
CREATE TABLE eq_shareholder (
    id               INTEGER PRIMARY KEY,
    shareholder_type TEXT NOT NULL CHECK (shareholder_type IN ('PERSON', 'ENTERPRISE')),
    person_id        INTEGER,
    enterprise_id    INTEGER,
    CHECK (
        (shareholder_type = 'PERSON' AND person_id IS NOT NULL AND enterprise_id IS NULL)
        OR (shareholder_type = 'ENTERPRISE' AND enterprise_id IS NOT NULL AND person_id IS NULL)
    ),
    FOREIGN KEY (person_id)     REFERENCES hr_employee(id),
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

-- 持股：股东 -> 被投企业，比例/出资额/日期/直接间接
-- 刻意异常：企业 1001 直接持股合计 60+45+55=160%、企业 1002 合计 70+35=105%
CREATE TABLE eq_equity_holding (
    id                       INTEGER PRIMARY KEY,
    shareholder_id           INTEGER NOT NULL,
    investee_enterprise_id   INTEGER NOT NULL,
    ownership_pct            REAL NOT NULL CHECK (ownership_pct >= 0),
    subscribed_amount        REAL,
    contribution_date        TEXT,
    holding_mode             TEXT NOT NULL CHECK (holding_mode IN ('DIRECT', 'INDIRECT')),
    FOREIGN KEY (shareholder_id)         REFERENCES eq_shareholder(id),
    FOREIGN KEY (investee_enterprise_id) REFERENCES enterprise(id)
);

-- 场景三：人物关系（上下级/同事/亲属）与高管任职
CREATE TABLE person_relation (
    id             INTEGER PRIMARY KEY,
    person_a_id    INTEGER NOT NULL,
    person_b_id    INTEGER NOT NULL,
    relation_type  TEXT NOT NULL CHECK (relation_type IN ('RELATIVE', 'COLLEAGUE', 'REPORTS_TO')),
    relation_label TEXT,
    CHECK (person_a_id <> person_b_id),
    FOREIGN KEY (person_a_id) REFERENCES hr_employee(id),
    FOREIGN KEY (person_b_id) REFERENCES hr_employee(id)
);

CREATE TABLE org_executive_role (
    id           INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL,
    enterprise_id INTEGER NOT NULL,
    role_name    TEXT NOT NULL,
    start_date   TEXT,
    end_date     TEXT,
    FOREIGN KEY (employee_id)   REFERENCES hr_employee(id),
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

-- 场景四：客商（customer/supplier 双表，同一信用代码承担双角色）
CREATE TABLE crm_customer (
    id            INTEGER PRIMARY KEY,
    enterprise_id INTEGER NOT NULL,
    credit_code   TEXT NOT NULL,
    name          TEXT NOT NULL,
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

CREATE TABLE crm_supplier (
    id            INTEGER PRIMARY KEY,
    enterprise_id INTEGER NOT NULL,
    credit_code   TEXT NOT NULL,
    name          TEXT NOT NULL,
    FOREIGN KEY (enterprise_id) REFERENCES enterprise(id)
);

CREATE TABLE crm_trade_transaction (
    id                    INTEGER PRIMARY KEY,
    own_enterprise_id     INTEGER NOT NULL,
    partner_enterprise_id INTEGER NOT NULL,
    direction             TEXT NOT NULL CHECK (direction IN ('PURCHASE', 'SALE')),
    amount                REAL NOT NULL,
    transaction_date      TEXT NOT NULL,
    order_no              TEXT NOT NULL UNIQUE,
    FOREIGN KEY (own_enterprise_id)     REFERENCES enterprise(id),
    FOREIGN KEY (partner_enterprise_id) REFERENCES enterprise(id)
);

-- ===== 灌数：五场景 =====

-- 部门树：1001 下两棵树（总部 4 层、研发 2 层）+ 孤儿 99（parent 9999 不存在）
INSERT INTO org_department (id, enterprise_id, parent_id, code, name) VALUES
    (10, 1001, NULL, 'HQ',        '总部'),
    (11, 1001, 10,   'OPS',       '运营中心'),
    (12, 1001, 11,   'OPS-IT',    '信息技术部'),
    (13, 1001, 12,   'OPS-IT-DATA', '数据组'),
    (14, 1001, NULL, 'RND',       '研发中心'),
    (15, 1001, 14,   'RND-AI',    '人工智能实验室');

INSERT INTO org_position (id, code, name) VALUES
    (1, 'CEO', '首席执行官'), (2, 'MGR', '部门负责人'),
    (3, 'ENG', '工程师'),     (4, 'PM',  '项目经理');

INSERT INTO org_employment (id, employee_id, department_id, position_id, manager_employee_id, start_date, end_date, is_primary) VALUES
    (1001, 8001, 10, 1, NULL, '2021-01-01', NULL,         1),
    (1002, 8002, 11, 2, 8001, '2022-01-01', NULL,         1),
    (1003, 8003, 12, 3, 8002, '2022-03-01', NULL,         1),
    (1004, 8004, 13, 3, 8003, '2023-01-01', NULL,         1),
    (1005, 8005, 14, 2, 8001, '2022-06-01', NULL,         1),
    (1006, 8006, 15, 3, 8005, '2023-02-01', '2024-12-31', 1),
    (1007, 8006, 12, 3, 8003, '2025-01-01', NULL,         1),
    (1008, 8007, 11, 4, 8002, '2024-01-01', NULL,         1);

-- 股东：自然人 + 企业多态；三层链 1005 -> 1003 -> 1002，交叉，环路 1002 <-> 1007
INSERT INTO eq_shareholder (id, shareholder_type, person_id, enterprise_id) VALUES
    (201, 'PERSON',     8001, NULL),
    (202, 'PERSON',     8002, NULL),
    (203, 'ENTERPRISE', NULL, 1002),
    (204, 'ENTERPRISE', NULL, 1003),
    (205, 'ENTERPRISE', NULL, 1007),
    (206, 'PERSON',     8003, NULL);

INSERT INTO eq_equity_holding (id, shareholder_id, investee_enterprise_id, ownership_pct, subscribed_amount, contribution_date, holding_mode) VALUES
    (3001, 201, 1001, 60.0, 6000000.0, '2021-01-10', 'DIRECT'),
    (3002, 202, 1001, 45.0, 4500000.0, '2021-01-10', 'DIRECT'),
    (3003, 203, 1001, 55.0, 5500000.0, '2021-02-01', 'DIRECT'),
    (3004, 204, 1002, 70.0, 7000000.0, '2021-03-01', 'DIRECT'),
    (3005, 205, 1003, 65.0, 6500000.0, '2021-04-01', 'DIRECT'),
    (3006, 203, 1007, 40.0, 4000000.0, '2022-01-01', 'DIRECT'),
    (3007, 205, 1002, 35.0, 3500000.0, '2022-01-02', 'DIRECT'),
    (3008, 206, 1003, 10.0, 1000000.0, '2022-02-02', 'DIRECT');

INSERT INTO person_relation (id, person_a_id, person_b_id, relation_type, relation_label) VALUES
    (501, 8001, 8002, 'REPORTS_TO', '直属上级'),
    (502, 8002, 8003, 'COLLEAGUE',  '同事'),
    (503, 8003, 8004, 'RELATIVE',   '兄妹'),
    (504, 8005, 8007, 'RELATIVE',   '配偶');

INSERT INTO org_executive_role (id, employee_id, enterprise_id, role_name, start_date, end_date) VALUES
    (601, 8001, 1001, '法定代表人', '2021-01-01', NULL),
    (602, 8002, 1002, '总经理',     '2022-01-01', NULL);

-- 客商：1006 同时是客户与供应商（信用代码 91310000DEMA000006 双角色融合样例）
INSERT INTO crm_customer (id, enterprise_id, credit_code, name) VALUES
    (701, 1005, '91310000DEMA000005', '测试云服务'),
    (702, 1006, '91310000DEMA000006', '示例数据工程');
INSERT INTO crm_supplier (id, enterprise_id, credit_code, name) VALUES
    (703, 1004, '91310000DEMA000004', '虚构智能科技'),
    (704, 1006, '91310000DEMA000006', '示例数据工程');

INSERT INTO crm_trade_transaction (id, own_enterprise_id, partner_enterprise_id, direction, amount, transaction_date, order_no) VALUES
    (801, 1001, 1004, 'PURCHASE', 1200000.0, '2024-02-01', 'PO-001'),
    (802, 1001, 1006, 'PURCHASE',  800000.0, '2024-03-15', 'PO-002'),
    (803, 1001, 1005, 'SALE',     2100000.0, '2024-04-20', 'SO-001'),
    (804, 1001, 1006, 'SALE',      500000.0, '2024-05-10', 'SO-002'),
    (805, 1001, 1004, 'PURCHASE',  300000.0, '2025-01-12', 'PO-003');

-- 合同签约方：6011 三方（含双角色客商 1006），其余两方
INSERT INTO ct_contract_party (id, contract_id, enterprise_id, party_role) VALUES
    (1, 6001, 1001, 'PARTY_A'),
    (2, 6001, 1004, 'PARTY_B'),
    (3, 6002, 1001, 'PARTY_A'),
    (4, 6002, 1005, 'PARTY_B'),
    (5, 6002, 1006, 'PARTY_C'),
    (6, 6015, 1001, 'PARTY_A'),
    (7, 6015, 1004, 'PARTY_B');

-- 索引（提升 M3 抽取与证据追溯查询）
CREATE INDEX idx_employee_enterprise ON hr_employee(enterprise_id);
CREATE INDEX idx_contract_project_project ON ct_contract_project(project_id);
CREATE INDEX idx_project_member_member ON pm_project_member(member_id);
CREATE INDEX idx_project_member_project ON pm_project_member(project_id);
CREATE INDEX idx_department_parent ON org_department(parent_id);
CREATE INDEX idx_employment_employee ON org_employment(employee_id);
CREATE INDEX idx_holding_shareholder ON eq_equity_holding(shareholder_id);
CREATE INDEX idx_holding_investee ON eq_equity_holding(investee_enterprise_id);
CREATE INDEX idx_transaction_partner ON crm_trade_transaction(partner_enterprise_id);
CREATE INDEX idx_contract_party_contract ON ct_contract_party(contract_id);
