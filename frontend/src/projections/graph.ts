import type {
  ClassObject,
  GraphObject,
  InstanceObject,
  RelationObject,
  RelationTypeObject,
} from "../api/types";

export interface ProjectionNodeData {
  id: string;
  objectId: string;
  kind: string;
  label: string;
  subtitle: string;
}

export interface ProjectionEdgeData {
  id: string;
  source: string;
  target: string;
  label: string;
  kind: string;
}

export interface ProjectionNode {
  data: ProjectionNodeData;
}

export interface ProjectionEdge {
  data: ProjectionEdgeData;
}

export type ProjectionElement = ProjectionNode | ProjectionEdge;

export interface Projection {
  elements: ProjectionElement[];
  nodeCount: number;
  edgeCount: number;
  hiddenCount: number;
  visibleInstanceIds: string[];
}

export function objectById(objects: GraphObject[]): Map<string, GraphObject> {
  return new Map(objects.map((object) => [object.id, object]));
}

export function objectLabel(object: GraphObject): string {
  if ("label" in object && object.label) return object.label;
  return `${object.kind} ${object.id.slice(0, 8)}`;
}

export function objectSubtitle(object: GraphObject): string {
  switch (object.kind) {
    case "class":
      return "class";
    case "relation_type":
      return "relation type";
    case "attribute_type":
      return "attribute type";
    case "instance":
      return "instance";
    case "relation":
      return "relation assertion";
    case "attribute_value":
      return "literal assertion";
    case "source_ref":
      return "source reference";
  }
}

function node(object: GraphObject, label = objectLabel(object)): ProjectionNode {
  return {
    data: {
      id: object.id,
      objectId: object.id,
      kind: object.kind,
      label,
      subtitle: objectSubtitle(object),
    },
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  label: string,
  kind: string,
): ProjectionEdge {
  return { data: { id, source, target, label, kind } };
}

export function buildModelProjection(objects: GraphObject[]): Projection {
  const index = objectById(objects);
  const classes = objects.filter((item): item is ClassObject => item.kind === "class");
  const relationTypes = objects.filter(
    (item): item is RelationTypeObject => item.kind === "relation_type",
  );
  const attributeTypes = objects.filter((item) => item.kind === "attribute_type");

  const elements: ProjectionElement[] = [];
  for (const item of classes) elements.push(node(item));
  for (const item of relationTypes) elements.push(node(item));
  for (const item of attributeTypes) elements.push(node(item));

  let hiddenCount = 0;
  for (const item of classes) {
    for (const parentId of item.parent_ids) {
      if (!index.has(parentId)) {
        hiddenCount += 1;
        continue;
      }
      elements.push(
        edge(
          `schema:subclass:${item.id}:${parentId}`,
          item.id,
          parentId,
          "subClassOf",
          "subclass",
        ),
      );
    }
  }
  for (const item of relationTypes) {
    for (const domainId of item.domain_ids) {
      if (!index.has(domainId)) {
        hiddenCount += 1;
        continue;
      }
      elements.push(
        edge(
          `schema:domain:${item.id}:${domainId}`,
          item.id,
          domainId,
          "domain",
          "domain",
        ),
      );
    }
    for (const rangeId of item.range_ids) {
      if (!index.has(rangeId)) {
        hiddenCount += 1;
        continue;
      }
      elements.push(
        edge(
          `schema:range:${item.id}:${rangeId}`,
          item.id,
          rangeId,
          "range",
          "range",
        ),
      );
    }
  }
  for (const item of attributeTypes) {
    if (item.kind !== "attribute_type") continue;
    for (const domainId of item.domain_ids) {
      if (!index.has(domainId)) {
        hiddenCount += 1;
        continue;
      }
      elements.push(
        edge(
          `schema:attr-domain:${item.id}:${domainId}`,
          item.id,
          domainId,
          "domain",
          "domain",
        ),
      );
    }
  }

  elements.sort((a, b) => a.data.id.localeCompare(b.data.id));
  return {
    elements,
    nodeCount: classes.length + relationTypes.length + attributeTypes.length,
    edgeCount: elements.length - (classes.length + relationTypes.length + attributeTypes.length),
    hiddenCount,
    visibleInstanceIds: [],
  };
}

export function descendantClassIds(
  classes: ClassObject[],
  rootId: string,
): Set<string> {
  const children = new Map<string, string[]>();
  for (const item of classes) {
    for (const parent of item.parent_ids) {
      const current = children.get(parent) ?? [];
      current.push(item.id);
      children.set(parent, current);
    }
  }
  const seen = new Set<string>();
  const queue = [rootId];
  while (queue.length) {
    const current = queue.shift()!;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const child of children.get(current) ?? []) queue.push(child);
  }
  return seen;
}

export function buildInstanceProjection(
  objects: GraphObject[],
  classFilterId: string | null,
): Projection {
  const index = objectById(objects);
  const classes = objects.filter((item): item is ClassObject => item.kind === "class");
  const relationTypes = new Map(
    objects
      .filter((item): item is RelationTypeObject => item.kind === "relation_type")
      .map((item) => [item.id, item]),
  );
  const allInstances = objects.filter(
    (item): item is InstanceObject => item.kind === "instance",
  );
  const allRelations = objects.filter(
    (item): item is RelationObject => item.kind === "relation",
  );

  const allowedClasses =
    classFilterId && index.get(classFilterId)?.kind === "class"
      ? descendantClassIds(classes, classFilterId)
      : null;

  const visibleInstances = allowedClasses
    ? allInstances.filter((item) =>
        item.class_ids.some((classId) => allowedClasses.has(classId)),
      )
    : allInstances;
  const visibleIds = new Set(visibleInstances.map((item) => item.id));
  const visibleRelations = allRelations.filter(
    (item) => visibleIds.has(item.source_id) && visibleIds.has(item.target_id),
  );

  const elements: ProjectionElement[] = [];
  for (const item of visibleInstances) {
    const classLabels = item.class_ids
      .map((classId) => {
        const classObject = index.get(classId);
        return classObject && "label" in classObject ? classObject.label : null;
      })
      .filter(Boolean)
      .join(" · ");
    elements.push(node(item, classLabels ? `${item.label}\n${classLabels}` : item.label));
  }
  for (const item of visibleRelations) {
    const relationType = relationTypes.get(item.relation_type_id);
    const label = relationType ? relationType.label : "relation";
    elements.push(
      edge(`relation:${item.id}`, item.source_id, item.target_id, label, "relation"),
    );
  }

  const hiddenCount =
    allInstances.length -
    visibleInstances.length +
    (allRelations.length - visibleRelations.length);

  return {
    elements,
    nodeCount: visibleInstances.length,
    edgeCount: visibleRelations.length,
    hiddenCount,
    visibleInstanceIds: visibleInstances.map((item) => item.id),
  };
}
