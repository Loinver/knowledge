export interface Asset {
  id: number
  name: string
  label: string
  definition: string
  domain: string
  status: 'DRAFT' | 'PUBLISHED'
  props: number
  relations: number
  revision: number
  updated: string
  violation: boolean
  iri: string
}
const rows: Array<[string, string, string, number, number, 'DRAFT' | 'PUBLISHED', string]> = [
  ['Employee', '员工', 'hr', 12, 4, 'PUBLISHED', '组织中的在职人员，关联部门、岗位与参与的项目。'],
  [
    'Department',
    '组织部门',
    'org',
    8,
    5,
    'PUBLISHED',
    '承担组织职能的业务单元，支持上下级层级关系。',
  ],
  [
    'Project',
    '项目',
    'projectDomain',
    16,
    6,
    'PUBLISHED',
    '具有明确目标、周期和交付成果的协作活动。',
  ],
  ['Position', '岗位', 'hr', 7, 3, 'PUBLISHED', '组织内定义职责、任职条件和能力要求的岗位。'],
  [
    'ProjectParticipation',
    '项目参与记录',
    'projectDomain',
    9,
    2,
    'DRAFT',
    '记录员工参与项目的角色、工作投入与参与时间。',
  ],
  [
    'SupplierQualificationReview',
    '供应商资质审查与年度复核记录',
    'procurement',
    18,
    4,
    'DRAFT',
    '归集供应商资质证明、有效期与年度复核结论。',
  ],
  ['Organization', '组织机构', 'org', 11, 3, 'PUBLISHED', '独立承担业务与治理责任的组织机构。'],
  [
    'Contract',
    '采购合同',
    'procurement',
    21,
    5,
    'PUBLISHED',
    '约定采购范围、交付条件及履约责任的合同。',
  ],
  ['Office', '办公地点', 'org', 6, 2, 'PUBLISHED', '组织使用的办公场所与空间。'],
  ['Skill', '专业技能', 'hr', 5, 2, 'PUBLISHED', '描述岗位要求与员工能力的专业技能。'],
  ['Milestone', '项目里程碑', 'projectDomain', 8, 2, 'DRAFT', '项目内用于检查进度的关键成果节点。'],
  [
    'Equipment',
    '生产设备与运维资产',
    'procurement',
    15,
    3,
    'PUBLISHED',
    '需要统一登记、使用和维护的生产设备。',
  ],
  ['Certificate', '专业资格证书', 'hr', 9, 2, 'PUBLISHED', '由资质机构颁发的专业资格凭证。'],
  ['CostCenter', '成本中心', 'org', 7, 3, 'DRAFT', '用于归集组织成本与预算执行的核算单元。'],
]
export const denseAssets: Asset[] = rows.map((r, i) => ({
  id: i + 1,
  name: r[0],
  label: r[1],
  domain: r[2],
  props: r[3],
  relations: r[4],
  status: r[5],
  definition: r[6],
  revision: r[5] === 'DRAFT' ? 0 : 3,
  updated: `2026-11-${String(26 - (i % 6))}`,
  violation: i === 5,
  iri: `https://example.org/enterprise/${r[0]}`,
}))
export const referenceAssets: Asset[] = [
  {
    id: 1,
    name: 'UiDraftfcfdf1846db5',
    label: 'UI 验收草稿',
    definition: '隔离验收数据中的草稿实体类型。',
    domain: 'org',
    status: 'DRAFT',
    props: 1,
    relations: 0,
    revision: 0,
    updated: '2026-11-23',
    violation: false,
    iri: 'https://example.org/ui85b0d1192420/UiDraftfcfdf1846db5',
  },
  {
    id: 3,
    name: 'UiPublished1c015b883d21',
    label: 'UI 验收已发布类型',
    definition: '隔离验收数据中的已发布实体类型。',
    domain: 'org',
    status: 'PUBLISHED',
    props: 1,
    relations: 1,
    revision: 1,
    updated: '2026-11-23',
    violation: false,
    iri: 'https://example.org/ui85b0d1192420/UiPublished1c015b883d21',
  },
]
export const fields = [
  { name: 'employeeId', label: '员工编号', type: 'string', required: true },
  { name: 'fullName', label: '姓名', type: 'string', required: true },
  { name: 'email', label: '工作邮箱', type: 'string', required: false },
  { name: 'joinDate', label: '入职日期', type: 'date', required: true },
  { name: 'employmentStatus', label: '任职状态', type: 'enum', required: true },
  { name: 'phone', label: '联系电话', type: 'string', required: false },
]
export const graphNodes = [
  { id: 7, x: 75, y: 70 },
  { id: 2, x: 75, y: 300 },
  { id: 4, x: 390, y: 70 },
  { id: 1, x: 390, y: 300 },
  { id: 3, x: 705, y: 300 },
  { id: 12, x: 705, y: 70 },
  { id: 10, x: 390, y: 530 },
]
export const graphEdges = [
  { from: 7, to: 2, label: '下设' },
  { from: 1, to: 2, label: '隶属' },
  { from: 1, to: 4, label: '担任' },
  { from: 1, to: 3, label: '参与' },
  { from: 3, to: 12, label: '使用设备' },
  { from: 1, to: 10, label: '具备' },
  { from: 4, to: 12, label: '操作设备' },
]
export const sampleRuns = [
  {
    id: 'RUN-20261126-004',
    label: '员工主数据同步',
    status: 'success',
    time: '11-26 09:42',
    rows: '2,486',
  },
  {
    id: 'RUN-20261126-003',
    label: '项目参与关系抽取',
    status: 'partial',
    time: '11-26 09:15',
    rows: '1,208',
  },
  {
    id: 'RUN-20261125-012',
    label: '供应商资质审查记录',
    status: 'failure',
    time: '11-25 18:30',
    rows: '—',
  },
  {
    id: 'RUN-20261125-011',
    label: '组织结构同步',
    status: 'success',
    time: '11-25 17:20',
    rows: '128',
  },
]
