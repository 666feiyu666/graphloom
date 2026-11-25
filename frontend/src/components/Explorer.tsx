import { useMemo, useState } from "react";
import type {
  ClassObject,
  GraphObject,
  GraphState,
  Kind,
  SourceRefObject,
} from "../api/types";
import { descendantClassIds, objectLabel } from "../projections/graph";
import type { Mode } from "../store/ui";

interface Props {
  state: GraphState;
  mode: Mode;
  selectedId: string | null;
  selectedClassId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onSelectClass: (id: string | null) => void;
  onCreate: (kind: Kind) => void;
}

const KIND_OPTIONS: { kind: Kind; label: string }[] = [
  { kind: "class", label: "Class" },
  { kind: "relation_type", label: "Relation type" },
  { kind: "attribute_type", label: "Attribute type" },
  { kind: "instance", label: "Instance" },
  { kind: "relation", label: "Relation" },
  { kind: "attribute_value", label: "Attribute value" },
  { kind: "source_ref", label: "Source reference" },
];

function matches(object: GraphObject, query: string): boolean {
  if (!query) return true;
  const values: string[] = [];
  for (const field of ["label", "definition", "notes", "citation_text"] as const) {
    const value = (object as unknown as Record<string, unknown>)[field];
    if (typeof value === "string") values.push(value);
  }
  if ("aliases" in object && Array.isArray(object.aliases)) values.push(...object.aliases);
  if (object.kind === "source_ref") values.push(object.locator.value);
  return values.join(" ").toLowerCase().includes(query);
}

function SectionHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="section-header">
      <h3>{title}</h3>
      <span>{count}</span>
    </div>
  );
}

export default function Explorer({
  state,
  mode,
  selectedId,
  selectedClassId,
  disabled,
  onSelect,
  onSelectClass,
  onCreate,
}: Props) {
  const [query, setQuery] = useState("");
  const [newKind, setNewKind] = useState<Kind>("class");
  const needle = query.trim().toLowerCase();

  const classes = useMemo(
    () =>
      state.objects
        .filter((object) => object.kind === "class" && matches(object, needle))
        .sort((a, b) => ("label" in a && "label" in b ? a.label.localeCompare(b.label) : 0)),
    [state.objects, needle],
  );
  const relationTypes = state.objects
    .filter((object) => object.kind === "relation_type" && matches(object, needle))
    .sort((a, b) => ("label" in a && "label" in b ? a.label.localeCompare(b.label) : 0));
  const attributeTypes = state.objects
    .filter((object) => object.kind === "attribute_type" && matches(object, needle))
    .sort((a, b) => ("label" in a && "label" in b ? a.label.localeCompare(b.label) : 0));
  const sourceRefs = state.objects
    .filter(
      (object): object is SourceRefObject =>
        object.kind === "source_ref" && matches(object, needle),
    )
    .sort((a, b) => ("label" in a && "label" in b ? a.label.localeCompare(b.label) : 0));
  const instances = state.objects
    .filter((object) => object.kind === "instance" && matches(object, needle))
    .sort((a, b) => ("label" in a && "label" in b ? a.label.localeCompare(b.label) : 0));

  const selectedClass = selectedClassId
    ? state.objects.find((object) => object.id === selectedClassId)
    : null;
  const allowedClasses = selectedClassId
    ? descendantClassIds(
        state.objects.filter((object) => object.kind === "class") as never,
        selectedClassId,
      )
    : null;
  const filteredInstances = allowedClasses
    ? instances.filter(
        (object) =>
          object.kind === "instance" &&
          object.class_ids.some((classId) => allowedClasses.has(classId)),
      )
    : instances;

  return (
    <aside className="explorer" aria-label="Project explorer">
      <div className="explorer-search">
        <label className="sr-only" htmlFor="explorer-search">
          Search objects
        </label>
        <input
          id="explorer-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search labels, definitions…"
        />
      </div>

      <div className="new-object">
        <label className="sr-only" htmlFor="new-kind">
          Kind to create
        </label>
        <select
          id="new-kind"
          value={newKind}
          onChange={(event) => setNewKind(event.target.value as Kind)}
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option.kind} value={option.kind}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          className="primary compact"
          onClick={() => onCreate(newKind)}
          disabled={disabled}
          title={disabled ? "Save or discard the current draft first" : "Create object"}
        >
          New
        </button>
      </div>

      <div className="explorer-scroll">
        <section>
          <SectionHeader title="Classes" count={classes.length} />
          <div className="tree-list">
            {classes.map((object) => (
              <div
                key={object.id}
                className={`tree-row ${selectedId === object.id ? "is-selected" : ""}`}
              >
                <button className="tree-main" onClick={() => onSelect(object.id)}>
                  <span className="kind-dot kind-class" />
                  <span className="row-label">{objectLabel(object)}</span>
                  {"parent_ids" in object && object.parent_ids.length > 0 && (
                    <span className="row-meta">{object.parent_ids.length}p</span>
                  )}
                </button>
                {mode === "instance" && (
                  <button
                    className="mini"
                    onClick={() =>
                      onSelectClass(selectedClassId === object.id ? null : object.id)
                    }
                    title="Filter instances by this class"
                  >
                    {selectedClassId === object.id ? "clear" : "instances"}
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>

        <section>
          <SectionHeader title="Relation types" count={relationTypes.length} />
          <div className="tree-list">
            {relationTypes.map((object) => (
              <button
                key={object.id}
                className={`tree-main ${selectedId === object.id ? "is-selected" : ""}`}
                onClick={() => onSelect(object.id)}
              >
                <span className="kind-dot kind-relation_type" />
                <span className="row-label">{objectLabel(object)}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <SectionHeader title="Attribute types" count={attributeTypes.length} />
          <div className="tree-list">
            {attributeTypes.map((object) => (
              <button
                key={object.id}
                className={`tree-main ${selectedId === object.id ? "is-selected" : ""}`}
                onClick={() => onSelect(object.id)}
              >
                <span className="kind-dot kind-attribute_type" />
                <span className="row-label">{objectLabel(object)}</span>
              </button>
            ))}
          </div>
        </section>

        <section>
          <SectionHeader title="Instances" count={filteredInstances.length} />
          {selectedClass && (
            <div className="filter-chip">
              <span>{objectLabel(selectedClass)}</span>
              <button onClick={() => onSelectClass(null)}>clear</button>
            </div>
          )}
          <div className="tree-list">
            {filteredInstances.map((object) => (
              <button
                key={object.id}
                className={`tree-main ${selectedId === object.id ? "is-selected" : ""}`}
                onClick={() => onSelect(object.id)}
              >
                <span className="kind-dot kind-instance" />
                <span className="row-label">{objectLabel(object)}</span>
              </button>
            ))}
          </div>
          {selectedClass && filteredInstances.length === 0 && (
            <p className="empty-note">No instances of this class or its descendants.</p>
          )}
        </section>

        <section>
          <SectionHeader title="Source references" count={sourceRefs.length} />
          <div className="tree-list">
            {sourceRefs.map((object) => (
              <button
                key={object.id}
                className={`tree-main ${selectedId === object.id ? "is-selected" : ""}`}
                onClick={() => onSelect(object.id)}
              >
                <span className="kind-dot kind-source_ref" />
                <span className="row-label">{objectLabel(object)}</span>
                <span className="row-meta">{object.evidence_state}</span>
              </button>
            ))}
          </div>
        </section>

        {state.objects.length === 0 && (
          <p className="empty-note">
            This project is empty. Create a class, a relation type, and an instance to begin a
            synthetic modeling trial.
          </p>
        )}
      </div>
    </aside>
  );
}
