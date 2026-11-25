import type { GraphObject, ValueType } from "./types";

const NAMED_KINDS = new Set(["class", "relation_type", "attribute_type", "instance"]);

export function splitAliases(value: unknown): string[] {
  if (typeof value !== "string") return [];
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function aliasesToText(aliases: string[]): string {
  return aliases.join("\n");
}

export function parseLiteral(value: unknown, valueType: ValueType): unknown {
  if (valueType === "number") {
    if (typeof value === "number") return value;
    const text = String(value ?? "").trim();
    if (!text) return value;
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : value;
  }
  if (valueType === "boolean") {
    if (typeof value === "boolean") return value;
    return String(value).toLowerCase() === "true";
  }
  return value;
}

export function validateLiteral(value: unknown, valueType: ValueType): string | null {
  const text = String(value ?? "").trim();
  if (valueType === "number") {
    if (!text || !Number.isFinite(Number(text))) return "数字类型的字面量必须填写有效数字";
  } else if (valueType === "boolean") {
    if (text !== "true" && text !== "false") return "布尔类型的字面量必须是 true 或 false";
  } else if (valueType === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return "日期必须使用 YYYY-MM-DD";
    const parsed = new Date(`${text}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== text) {
      return "日期不是有效的日历日期";
    }
  } else if (valueType === "uri") {
    if (!text) return "URI 类型的字面量不能为空";
  }
  return null;
}

export function defaultValues(kind: string): Record<string, unknown> {
  const common = {
    notes: "",
    source_ref_ids: [] as string[],
    review_status: "proposed",
    lifecycle: "active",
  };
  switch (kind) {
    case "class":
      return {
        ...common,
        label: "",
        definition: "",
        aliases: "",
        parent_ids: [] as string[],
      };
    case "relation_type":
      return {
        ...common,
        label: "",
        definition: "",
        aliases: "",
        domain_ids: [] as string[],
        range_ids: [] as string[],
      };
    case "attribute_type":
      return {
        ...common,
        label: "",
        definition: "",
        aliases: "",
        domain_ids: [] as string[],
        value_type: "string" as ValueType,
      };
    case "instance":
      return {
        ...common,
        label: "",
        definition: "",
        aliases: "",
        class_ids: [] as string[],
      };
    case "relation":
      return { ...common, source_id: "", relation_type_id: "", target_id: "" };
    case "attribute_value":
      return { ...common, subject_id: "", attribute_type_id: "", value: "" };
    case "source_ref":
      return {
        ...common,
        label: "",
        locator_kind: "url",
        locator_value: "",
        citation_text: "",
        evidence_state: "unverified",
      };
    default:
      return { ...common };
  }
}

export function valuesFromObject(object: GraphObject): Record<string, unknown> {
  const common = {
    notes: object.notes,
    source_ref_ids: [...object.source_ref_ids],
    review_status: object.review_status,
    lifecycle: object.lifecycle,
  };
  switch (object.kind) {
    case "class":
      return {
        ...common,
        label: object.label,
        definition: object.definition,
        aliases: aliasesToText(object.aliases),
        parent_ids: [...object.parent_ids],
      };
    case "relation_type":
      return {
        ...common,
        label: object.label,
        definition: object.definition,
        aliases: aliasesToText(object.aliases),
        domain_ids: [...object.domain_ids],
        range_ids: [...object.range_ids],
      };
    case "attribute_type":
      return {
        ...common,
        label: object.label,
        definition: object.definition,
        aliases: aliasesToText(object.aliases),
        domain_ids: [...object.domain_ids],
        value_type: object.value_type,
      };
    case "instance":
      return {
        ...common,
        label: object.label,
        definition: object.definition,
        aliases: aliasesToText(object.aliases),
        class_ids: [...object.class_ids],
      };
    case "relation":
      return {
        ...common,
        source_id: object.source_id,
        relation_type_id: object.relation_type_id,
        target_id: object.target_id,
      };
    case "attribute_value":
      return {
        ...common,
        subject_id: object.subject_id,
        attribute_type_id: object.attribute_type_id,
        value: object.value === null ? "" : String(object.value),
      };
    case "source_ref":
      return {
        ...common,
        label: object.label,
        locator_kind: object.locator.kind,
        locator_value: object.locator.value,
        citation_text: object.citation_text,
        evidence_state: object.evidence_state,
      };
  }
}

function baseNamed(values: Record<string, unknown>) {
  return {
    label: String(values.label ?? "").trim(),
    definition: String(values.definition ?? ""),
    aliases: splitAliases(values.aliases),
    notes: String(values.notes ?? ""),
    source_ref_ids: (values.source_ref_ids as string[]) ?? [],
    review_status: values.review_status ?? "proposed",
    lifecycle: values.lifecycle ?? "active",
  };
}

function baseAssertion(values: Record<string, unknown>) {
  return {
    notes: String(values.notes ?? ""),
    source_ref_ids: (values.source_ref_ids as string[]) ?? [],
    review_status: values.review_status ?? "proposed",
    lifecycle: values.lifecycle ?? "active",
  };
}

export function draftToCreateData(
  kind: string,
  values: Record<string, unknown>,
  valueType: ValueType = "string",
): Record<string, unknown> {
  switch (kind) {
    case "class":
      return {
        ...baseNamed(values),
        parent_ids: (values.parent_ids as string[]) ?? [],
      };
    case "relation_type":
      return {
        ...baseNamed(values),
        domain_ids: (values.domain_ids as string[]) ?? [],
        range_ids: (values.range_ids as string[]) ?? [],
      };
    case "attribute_type":
      return {
        ...baseNamed(values),
        domain_ids: (values.domain_ids as string[]) ?? [],
        value_type: values.value_type ?? "string",
      };
    case "instance":
      return {
        ...baseNamed(values),
        class_ids: (values.class_ids as string[]) ?? [],
      };
    case "relation":
      return {
        ...baseAssertion(values),
        source_id: values.source_id ?? "",
        relation_type_id: values.relation_type_id ?? "",
        target_id: values.target_id ?? "",
      };
    case "attribute_value":
      return {
        ...baseAssertion(values),
        subject_id: values.subject_id ?? "",
        attribute_type_id: values.attribute_type_id ?? "",
        value: parseLiteral(values.value, valueType),
      };
    case "source_ref":
      return {
        label: String(values.label ?? "").trim(),
        locator: {
          kind: values.locator_kind ?? "url",
          value: String(values.locator_value ?? ""),
        },
        citation_text: String(values.citation_text ?? ""),
        evidence_state: values.evidence_state ?? "unverified",
        notes: String(values.notes ?? ""),
        source_ref_ids: (values.source_ref_ids as string[]) ?? [],
        review_status: values.review_status ?? "proposed",
        lifecycle: values.lifecycle ?? "active",
      };
    default:
      return { ...values };
  }
}

function different(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) !== JSON.stringify(b);
}

export function draftToUpdateFields(
  kind: string,
  values: Record<string, unknown>,
  original: Record<string, unknown>,
  valueType: ValueType = "string",
): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  const assign = (key: string, value: unknown) => {
    if (different(value, original[key])) fields[key] = value;
  };

  if (kind === "source_ref") {
    assign("label", String(values.label ?? "").trim());
    if (
      different(values.locator_kind, original.locator_kind) ||
      different(values.locator_value, original.locator_value)
    ) {
      fields.locator = {
        kind: values.locator_kind ?? "url",
        value: String(values.locator_value ?? ""),
      };
    }
    assign("citation_text", String(values.citation_text ?? ""));
    assign("evidence_state", values.evidence_state ?? "unverified");
    assign("notes", String(values.notes ?? ""));
    assign("source_ref_ids", values.source_ref_ids ?? []);
    assign("review_status", values.review_status ?? "proposed");
    assign("lifecycle", values.lifecycle ?? "active");
    return fields;
  }

  if (kind === "relation" || kind === "attribute_value") {
    if (kind === "relation") {
      assign("source_id", values.source_id ?? "");
      assign("relation_type_id", values.relation_type_id ?? "");
      assign("target_id", values.target_id ?? "");
    } else {
      assign("subject_id", values.subject_id ?? "");
      assign("attribute_type_id", values.attribute_type_id ?? "");
      assign("value", parseLiteral(values.value, valueType));
    }
    assign("notes", String(values.notes ?? ""));
    assign("source_ref_ids", values.source_ref_ids ?? []);
    assign("review_status", values.review_status ?? "proposed");
    assign("lifecycle", values.lifecycle ?? "active");
    return fields;
  }

  if (NAMED_KINDS.has(kind)) {
    assign("label", String(values.label ?? "").trim());
    assign("definition", String(values.definition ?? ""));
    assign("aliases", splitAliases(values.aliases));
    assign("notes", String(values.notes ?? ""));
    assign("source_ref_ids", values.source_ref_ids ?? []);
    assign("review_status", values.review_status ?? "proposed");
    assign("lifecycle", values.lifecycle ?? "active");
    if (kind === "class") assign("parent_ids", values.parent_ids ?? []);
    if (kind === "relation_type") {
      assign("domain_ids", values.domain_ids ?? []);
      assign("range_ids", values.range_ids ?? []);
    }
    if (kind === "attribute_type") {
      assign("domain_ids", values.domain_ids ?? []);
      assign("value_type", values.value_type ?? "string");
    }
    if (kind === "instance") assign("class_ids", values.class_ids ?? []);
  }
  return fields;
}

export function validateDraft(
  kind: string,
  values: Record<string, unknown>,
  valueType: ValueType = "string",
): string | null {
  if (NAMED_KINDS.has(kind) && !String(values.label ?? "").trim()) {
    return "标签不能为空";
  }
  if (kind === "source_ref") {
    if (!String(values.label ?? "").trim()) return "来源标签不能为空";
    if (!String(values.locator_value ?? "").trim()) return "定位符不能为空";
  }
  if (kind === "relation") {
    if (!values.source_id || !values.relation_type_id || !values.target_id) {
      return "关系断言需要源实例、关系类型和目标实例";
    }
  }
  if (kind === "attribute_value") {
    if (!values.subject_id || !values.attribute_type_id) {
      return "字面量断言需要主体实例和属性类型";
    }
    return validateLiteral(values.value, valueType);
  }
  if (kind === "attribute_type" && !values.value_type) {
    return "属性类型需要 value_type";
  }
  return null;
}

export function deriveValueType(
  values: Record<string, unknown>,
  objects: GraphObject[],
): ValueType {
  const attributeTypeId = values.attribute_type_id;
  const attributeType = objects.find(
    (object) => object.kind === "attribute_type" && object.id === attributeTypeId,
  );
  return attributeType?.kind === "attribute_type" ? attributeType.value_type : "string";
}
