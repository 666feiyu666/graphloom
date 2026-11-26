import { useMemo, useState } from "react";
import type { GraphObject, Kind, Warning } from "../api/types";
import { objectById, objectLabel } from "../projections/graph";

interface Props {
  objects: GraphObject[];
  selectedId: string | null;
  warnings: Warning[];
  onSelect: (id: string) => void;
  onEdit: (object: GraphObject) => void;
}

const KIND_FILTERS: { value: Kind | "all"; label: string }[] = [
  { value: "all", label: "All kinds" },
  { value: "class", label: "Classes" },
  { value: "relation_type", label: "Relation types" },
  { value: "attribute_type", label: "Attribute types" },
  { value: "instance", label: "Instances" },
  { value: "relation", label: "Relations" },
  { value: "attribute_value", label: "Attribute values" },
  { value: "source_ref", label: "Source references" },
];

function summary(object: GraphObject, index: Map<string, GraphObject>): string {
  if (object.kind === "relation") {
    const source = index.get(object.source_id);
    const target = index.get(object.target_id);
    const relationType = index.get(object.relation_type_id);
    return `${source ? objectLabel(source) : object.source_id.slice(0, 8)} → ${
      target ? objectLabel(target) : object.target_id.slice(0, 8)
    }${relationType ? ` · ${objectLabel(relationType)}` : ""}`;
  }
  if (object.kind === "attribute_value") {
    const subject = index.get(object.subject_id);
    const attributeType = index.get(object.attribute_type_id);
    return `${subject ? objectLabel(subject) : object.subject_id.slice(0, 8)} · ${
      attributeType ? objectLabel(attributeType) : object.attribute_type_id.slice(0, 8)
    }: ${String(object.value)}`;
  }
  return objectLabel(object);
}

function description(object: GraphObject): string {
  if (object.kind === "relation" || object.kind === "attribute_value") return object.notes;
  if (object.kind === "source_ref") return object.citation_text || object.locator.value;
  return object.definition;
}

export default function TableView({ objects, selectedId, warnings, onSelect, onEdit }: Props) {
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState<Kind | "all">("all");
  const index = useMemo(() => objectById(objects), [objects]);
  const warningIds = useMemo(
    () => new Set(warnings.map((warning) => warning.object_id).filter(Boolean)),
    [warnings],
  );

  const rows = objects
    .filter((object) => kindFilter === "all" || object.kind === kindFilter)
    .filter((object) => {
      if (!query.trim()) return true;
      const needle = query.trim().toLowerCase();
      return `${summary(object, index)} ${description(object)}`.toLowerCase().includes(needle);
    })
    .sort((a, b) => a.kind.localeCompare(b.kind) || summary(a, index).localeCompare(summary(b, index)));

  return (
    <section className="table-view" aria-label="Table view">
      <div className="table-toolbar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter rows…"
          aria-label="Filter table rows"
        />
        <select
          value={kindFilter}
          onChange={(event) => setKindFilter(event.target.value as Kind | "all")}
          aria-label="Filter by kind"
        >
          {KIND_FILTERS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <span className="muted">{rows.length} rows</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Kind</th>
              <th>Object</th>
              <th>Definition / value</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((object) => (
              <tr
                key={object.id}
                className={selectedId === object.id ? "is-selected" : ""}
                onClick={() => onSelect(object.id)}
              >
                <td>
                  <span className={`kind-badge kind-${object.kind}`}>
                    {object.kind.replaceAll("_", " ")}
                  </span>
                </td>
                <td>
                  <span className="table-object">
                    {warningIds.has(object.id) && (
                      <span className="warning-dot" title="Advisory warning" />
                    )}
                    {summary(object, index)}
                  </span>
                </td>
                <td className="table-description">{description(object) || "—"}</td>
                <td>{object.status}</td>
                <td>
                  <button
                    className="mini"
                    onClick={(event) => {
                      event.stopPropagation();
                      onEdit(object);
                    }}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty-note">No rows match this filter.</p>}
      </div>
    </section>
  );
}
