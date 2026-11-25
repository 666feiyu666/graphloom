export type Kind =
  | "class"
  | "relation_type"
  | "attribute_type"
  | "instance"
  | "relation"
  | "attribute_value"
  | "source_ref";

export type ReviewStatus = "proposed" | "accepted" | "questioned";
export type Lifecycle = "active" | "deprecated";
export type Origin = "human" | "import";
export type EvidenceState =
  | "discovered"
  | "bibliographically_verified"
  | "abstract_preview_verified"
  | "full_text_verified"
  | "secondary_only"
  | "unverified";
export type ValueType = "string" | "number" | "boolean" | "date" | "uri";
export type LocatorKind = "url" | "workspace_relative_path" | "zotero_key" | "free_text";
export type JsonValue = string | number | boolean | null;

export interface Locator {
  kind: LocatorKind;
  value: string;
}

export interface BaseObject {
  id: string;
  project_id: string;
  kind: Kind;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  origin: Origin;
  review_status: ReviewStatus;
  lifecycle: Lifecycle;
  notes: string;
  source_ref_ids: string[];
}

export interface NamedObject extends BaseObject {
  label: string;
  definition: string;
  aliases: string[];
}

export interface ClassObject extends NamedObject {
  kind: "class";
  parent_ids: string[];
}

export interface RelationTypeObject extends NamedObject {
  kind: "relation_type";
  domain_ids: string[];
  range_ids: string[];
}

export interface AttributeTypeObject extends NamedObject {
  kind: "attribute_type";
  domain_ids: string[];
  value_type: ValueType;
}

export interface InstanceObject extends NamedObject {
  kind: "instance";
  class_ids: string[];
}

export interface RelationObject extends BaseObject {
  kind: "relation";
  source_id: string;
  relation_type_id: string;
  target_id: string;
}

export interface AttributeValueObject extends BaseObject {
  kind: "attribute_value";
  subject_id: string;
  attribute_type_id: string;
  value: JsonValue;
}

export interface SourceRefObject extends BaseObject {
  kind: "source_ref";
  label: string;
  locator: Locator;
  citation_text: string;
  evidence_state: EvidenceState;
}

export type GraphObject =
  | ClassObject
  | RelationTypeObject
  | AttributeTypeObject
  | InstanceObject
  | RelationObject
  | AttributeValueObject
  | SourceRefObject;

export interface ProjectCounts {
  objects: number;
  classes: number;
  instances: number;
  relations: number;
  assertions: number;
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  current_revision: number;
  created_at: string | null;
  updated_at: string | null;
  counts: ProjectCounts;
}

export interface GraphState {
  format_version: number;
  project_id: string;
  project_name: string;
  revision: number;
  objects: GraphObject[];
}

export interface Warning {
  code: string;
  message: string;
  object_id?: string;
  field?: string;
  details?: Record<string, unknown>;
}

export interface SchemaResponse {
  project_id: string;
  revision: number;
  classes: ClassObject[];
  relation_types: RelationTypeObject[];
  attribute_types: AttributeTypeObject[];
  source_refs: SourceRefObject[];
  warnings: Warning[];
  counts: {
    classes: number;
    relation_types: number;
    attribute_types: number;
    source_refs: number;
  };
}

export interface ObjectsResponse {
  project_id: string;
  revision: number;
  kind: Kind | null;
  q: string;
  objects: GraphObject[];
  returned_count: number;
  total_matching: number;
  has_more: boolean;
  next_cursor: string | null;
}

export interface Capabilities {
  role: "owner" | "reader";
  actor: string;
  read_only: boolean;
  api_version: string;
  format_versions: Record<string, number[]>;
  limits: {
    page_size_default: number;
    page_size_max: number;
    query_objects_max: number;
    neighborhood_depth_max: number;
    body_bytes_max: number;
  };
  kinds: Kind[];
  operations: string[];
  project_scope: "all" | string[];
  value_types: ValueType[];
  evidence_states: EvidenceState[];
}

export interface DiffEntry {
  id: string;
  kind: Kind;
  label: string;
  object: GraphObject;
}

export interface ChangedEntry {
  id: string;
  kind: Kind;
  label: string;
  fields: Record<string, { before: unknown; after: unknown }>;
}

export interface Diff {
  from_revision: number;
  to_revision: number;
  added: DiffEntry[];
  removed: DiffEntry[];
  changed: ChangedEntry[];
  counts: { added: number; removed: number; changed: number };
}

export interface Impacted {
  object_ids: string[];
  instance_ids: string[];
  assertion_ids: string[];
  warning_counts: { before: number; after: number };
  warnings_added: string[];
  warnings_removed: string[];
}

export type Operation =
  | { op: "create"; ref: string; kind: Kind; data: Record<string, unknown> }
  | { op: "update"; id: string; fields: Record<string, unknown> }
  | { op: "delete"; id: string };

export interface ChangeSet {
  id: string;
  project_id: string;
  base_revision: number;
  status: "prepared" | "invalid" | "committed";
  payload_hash: string;
  operations: Operation[] | Record<string, unknown>;
  diff: Diff;
  impacted: Impacted;
  errors: Warning[];
  warnings: Warning[];
  id_map: Record<string, string>;
  reason: string;
  actor: string;
  created_at: string | null;
  committed_revision: number | null;
}

export interface CommitResult {
  project_id: string;
  revision: number;
  changed: boolean;
  change_set_id: string;
  diff: Diff;
  warnings: Warning[];
  id_map: Record<string, string>;
  idempotent_replay?: boolean;
}

export interface Revision {
  id: string;
  revision: number;
  actor: string;
  reason: string;
  change_set_id: string | null;
  created_at: string | null;
  diff: Diff;
}

export interface RevisionsResponse {
  project_id: string;
  current_revision: number;
  revisions: Revision[];
}

export interface Snapshot {
  id: string;
  name: string;
  revision: number;
  created_at: string | null;
}

export interface SnapshotsResponse {
  project_id: string;
  snapshots: Snapshot[];
}

export interface LayoutData {
  positions?: Record<string, { x: number; y: number }>;
  viewport?: { zoom: number; pan: { x: number; y: number } };
}

export interface LayoutResponse {
  project_id: string;
  version: number;
  data: LayoutData;
  updated_at?: string | null;
}

export interface Credential {
  id: string;
  role: "owner" | "reader";
  label: string;
  project_ids: string[];
  created_at: string | null;
  revoked_at: string | null;
  token?: string;
  token_notice?: string;
}

export interface CredentialsResponse {
  credentials: Credential[];
}

export interface NativeExport {
  format: "graphloom-native";
  format_version: number;
  exported_at: string;
  project: {
    id: string;
    name: string;
    description: string;
    revision: number;
  };
  graph: {
    format_version: number;
    project_id: string;
    revision: number;
    objects: GraphObject[];
  };
  layout?: LayoutData;
}
