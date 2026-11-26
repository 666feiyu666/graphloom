export type Kind =
  | "class"
  | "relation_type"
  | "attribute_type"
  | "instance"
  | "relation"
  | "attribute_value"
  | "source_ref";

export type Status = "active" | "deprecated";
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
  status: Status;
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
  version: number;
  saved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  counts: ProjectCounts;
}

export interface GraphState {
  format_version: number;
  project_id: string;
  project_name: string;
  version: number;
  saved_at: string | null;
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
  version: number;
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
  version: number;
  kind: Kind | null;
  q: string;
  objects: GraphObject[];
  returned_count: number;
  total_matching: number;
  has_more: boolean;
  next_cursor: string | null;
}

export interface Capabilities {
  api_version: string;
  read_only: boolean;
  limits: {
    page_size_default: number;
    page_size_max: number;
    query_objects_max: number;
    neighborhood_depth_max: number;
    body_bytes_max: number;
  };
  kinds: Kind[];
  value_types: ValueType[];
  evidence_states: EvidenceState[];
}

export type Operation =
  | { op: "create"; ref: string; kind: Kind; data: Record<string, unknown> }
  | { op: "update"; id: string; fields: Record<string, unknown> }
  | { op: "delete"; id: string };

export interface BatchResult {
  project_id: string;
  version: number;
  changed: boolean;
  added_ids: string[];
  updated_ids: string[];
  deleted_ids: string[];
  id_map: Record<string, string>;
  warnings: Warning[];
}

export interface LayoutData {
  positions?: Record<string, { x: number; y: number }>;
  viewport?: { zoom: number; pan: { x: number; y: number } };
}

export interface LayoutResponse {
  project_id: string;
  data: LayoutData;
}
