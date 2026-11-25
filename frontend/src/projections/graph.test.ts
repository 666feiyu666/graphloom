import { describe, expect, it } from "vitest";
import type { ClassObject, GraphObject, InstanceObject, RelationObject, RelationTypeObject } from "../api/types";
import { buildInstanceProjection, buildModelProjection, descendantClassIds } from "./graph";

const base = {
  project_id: "project-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  created_by: "owner",
  updated_by: "owner",
  origin: "human" as const,
  review_status: "proposed" as const,
  lifecycle: "active" as const,
  notes: "",
  source_ref_ids: [],
};

const category: ClassObject = {
  ...base,
  id: "class-category",
  kind: "class",
  label: "Category",
  definition: "Synthetic.",
  aliases: [],
  parent_ids: [],
};

const subcategory: ClassObject = {
  ...base,
  id: "class-sub",
  kind: "class",
  label: "Subcategory",
  definition: "Synthetic.",
  aliases: [],
  parent_ids: ["class-category"],
};

const relationType: RelationTypeObject = {
  ...base,
  id: "rel-type",
  kind: "relation_type",
  label: "Points to",
  definition: "Synthetic.",
  aliases: [],
  domain_ids: ["class-category"],
  range_ids: ["class-category"],
};

const alpha: InstanceObject = {
  ...base,
  id: "instance-alpha",
  kind: "instance",
  label: "Alpha",
  definition: "Synthetic.",
  aliases: [],
  class_ids: ["class-sub"],
};

const beta: InstanceObject = {
  ...base,
  id: "instance-beta",
  kind: "instance",
  label: "Beta",
  definition: "Synthetic.",
  aliases: [],
  class_ids: [],
};

const relation: RelationObject = {
  ...base,
  id: "relation-one",
  kind: "relation",
  source_id: "instance-alpha",
  relation_type_id: "rel-type",
  target_id: "instance-beta",
};

const objects: GraphObject[] = [category, subcategory, relationType, alpha, beta, relation];

describe("graph projections", () => {
  it("builds derived schema edges without treating them as assertions", () => {
    const projection = buildModelProjection(objects);
    expect(projection.nodeCount).toBe(3);
    expect(projection.edgeCount).toBe(3);
    const kinds = projection.elements.map((item) => item.data.id);
    expect(kinds).toContain("schema:subclass:class-sub:class-category");
    expect(kinds).toContain("schema:domain:rel-type:class-category");
    expect(kinds).toContain("schema:range:rel-type:class-category");
  });

  it("includes descendant classes in an instance filter", () => {
    expect(descendantClassIds([category, subcategory], "class-category")).toEqual(
      new Set(["class-category", "class-sub"]),
    );
    const projection = buildInstanceProjection(objects, "class-category");
    expect(projection.visibleInstanceIds).toEqual(["instance-alpha"]);
    const nodeIds = projection.elements.map((item) => item.data.id);
    expect(nodeIds).toContain("instance-alpha");
    expect(nodeIds).not.toContain("instance-beta");
    expect(nodeIds).not.toContain("relation-one");
  });

  it("keeps relation edges only when both endpoints are visible", () => {
    const projection = buildInstanceProjection(objects, null);
    const edgeIds = projection.elements
      .filter((item) => "source" in item.data)
      .map((item) => item.data.id);
    expect(edgeIds).toEqual(["relation:relation-one"]);
    expect(projection.hiddenCount).toBe(0);
  });
});
