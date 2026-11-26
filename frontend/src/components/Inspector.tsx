import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { deriveValueType } from "../api/draft";
import type {
  AttributeValueObject,
  ClassObject,
  GraphObject,
  GraphState,
  InstanceObject,
  RelationObject,
  RelationTypeObject,
  SchemaResponse,
  SourceRefObject,
  Warning,
} from "../api/types";
import { descendantClassIds, objectLabel } from "../projections/graph";
import type { Draft } from "../ui";

interface Props {
  state: GraphState;
  schema: SchemaResponse;
  selected: GraphObject | null;
  draft: Draft | null;
  warnings: Warning[];
  busy: boolean;
  error: string | null;
  onEdit: () => void;
  onUpdateDraft: (field: string, value: unknown) => void;
  onSave: () => void;
  onCancel: () => void;
  onDelete: (object: GraphObject) => void;
  onToggleStatus: (object: GraphObject) => void;
  onAddRelation: (subjectId?: string) => void;
  onAddAttribute: (subjectId?: string) => void;
  onSelect: (id: string) => void;
}

const STATUSES = ["active", "deprecated"] as const;
const EVIDENCE_STATES = [
  "discovered",
  "bibliographically_verified",
  "abstract_preview_verified",
  "full_text_verified",
  "secondary_only",
  "unverified",
] as const;
const LOCATOR_KINDS = ["url", "workspace_relative_path", "zotero_key", "free_text"] as const;
const VALUE_TYPES = ["string", "number", "boolean", "date", "uri"] as const;

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

function Referenced({ id, objects, onSelect }: { id: string; objects: GraphObject[]; onSelect: (id: string) => void }) {
  const object = objects.find((item) => item.id === id);
  return (
    <button className="object-link" onClick={() => onSelect(id)}>
      {object ? objectLabel(object) : `${id.slice(0, 8)}…`}
    </button>
  );
}

function IdList({ ids, objects, onSelect }: { ids: string[]; objects: GraphObject[]; onSelect: (id: string) => void }) {
  if (!ids.length) return <span className="muted">none</span>;
  return (
    <div className="chip-row">
      {ids.map((id) => (
        <Referenced key={id} id={id} objects={objects} onSelect={onSelect} />
      ))}
    </div>
  );
}

function WarningList({ warnings }: { warnings: Warning[] }) {
  if (!warnings.length) return null;
  return (
    <div className="warning-panel">
      <p className="eyebrow">Advisory warnings</p>
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${warning.code}-${warning.object_id}-${warning.field}-${index}`}>
            <strong>{warning.code}</strong> · {warning.message}
          </li>
        ))}
      </ul>
      <p className="fine-print">
        Warnings do not block exploratory modeling. Missing definitions and unverified references
        remain visible in the read API.
      </p>
    </div>
  );
}

function Metadata({ object }: { object: GraphObject }) {
  return (
    <dl className="metadata">
      <div>
        <dt>ID</dt>
        <dd><code>{object.id}</code></dd>
      </div>
      <div>
        <dt>Status</dt>
        <dd>{object.status}</dd>
      </div>
      <div>
        <dt>Created</dt>
        <dd>{object.created_at}</dd>
      </div>
      <div>
        <dt>Updated</dt>
        <dd>{object.updated_at}</dd>
      </div>
    </dl>
  );
}

function MultiSelect({
  value,
  options,
  onChange,
}: {
  value: string[];
  options: { id: string; label: string }[];
  onChange: (value: string[]) => void;
}) {
  return (
    <select
      multiple
      size={Math.min(6, Math.max(3, options.length))}
      value={value}
      onChange={(event) =>
        onChange(Array.from(event.target.selectedOptions).map((option) => option.value))
      }
    >
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function DraftForm({
  draft,
  state,
  schema,
  busy,
  error,
  warnings,
  onUpdateDraft,
  onSave,
  onCancel,
}: {
  draft: Draft;
  state: GraphState;
  schema: SchemaResponse;
  busy: boolean;
  error: string | null;
  warnings: Warning[];
  onUpdateDraft: (field: string, value: unknown) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const values = draft.values;
  const classes = schema.classes.map((item) => ({ id: item.id, label: item.label }));
  const relationTypes = schema.relation_types.map((item) => ({ id: item.id, label: item.label }));
  const attributeTypes = schema.attribute_types.map((item) => ({ id: item.id, label: item.label }));
  const instances = state.objects
    .filter((item): item is InstanceObject => item.kind === "instance")
    .map((item) => ({ id: item.id, label: item.label }));
  const sourceRefs = schema.source_refs.map((item) => ({ id: item.id, label: item.label }));
  const valueType = deriveValueType(values, state.objects);
  const named = ["class", "relation_type", "attribute_type", "instance"].includes(draft.kind);
  const isAssertion = draft.kind === "relation" || draft.kind === "attribute_value";

  return (
    <div className="inspector-body">
      <div className="inspector-title">
        <span className={`kind-badge kind-${draft.kind}`}>{draft.kind.replaceAll("_", " ")}</span>
        <h2>{draft.mode === "create" ? "New object" : "Edit object"}</h2>
      </div>

      {named && (
        <>
          <Field label="Label">
            <input value={String(values.label ?? "")} onChange={(event) => onUpdateDraft("label", event.target.value)} />
          </Field>
          <Field label="Definition" hint="A working definition; missing definitions stay visible as warnings.">
            <textarea rows={3} value={String(values.definition ?? "")} onChange={(event) => onUpdateDraft("definition", event.target.value)} />
          </Field>
          <Field label="Aliases" hint="One alias per line.">
            <textarea rows={2} value={String(values.aliases ?? "")} onChange={(event) => onUpdateDraft("aliases", event.target.value)} />
          </Field>
        </>
      )}

      {draft.kind === "class" && (
        <Field label="Parent classes" hint="Multiple parents are allowed; cycles are rejected.">
          <MultiSelect value={(values.parent_ids as string[]) ?? []} options={classes} onChange={(next) => onUpdateDraft("parent_ids", next)} />
        </Field>
      )}

      {draft.kind === "relation_type" && (
        <>
          <Field label="Domain classes" hint="Empty means unrestricted. Multiple classes mean any listed class or descendant.">
            <MultiSelect value={(values.domain_ids as string[]) ?? []} options={classes} onChange={(next) => onUpdateDraft("domain_ids", next)} />
          </Field>
          <Field label="Range classes" hint="Empty means unrestricted.">
            <MultiSelect value={(values.range_ids as string[]) ?? []} options={classes} onChange={(next) => onUpdateDraft("range_ids", next)} />
          </Field>
        </>
      )}

      {draft.kind === "attribute_type" && (
        <>
          <Field label="Domain classes" hint="Empty means unrestricted.">
            <MultiSelect value={(values.domain_ids as string[]) ?? []} options={classes} onChange={(next) => onUpdateDraft("domain_ids", next)} />
          </Field>
          <Field label="Value type">
            <select value={String(values.value_type ?? "string")} onChange={(event) => onUpdateDraft("value_type", event.target.value)}>
              {VALUE_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </Field>
        </>
      )}

      {draft.kind === "instance" && (
        <Field label="Classes" hint="An instance may remain untyped while the model is exploratory.">
          <MultiSelect value={(values.class_ids as string[]) ?? []} options={classes} onChange={(next) => onUpdateDraft("class_ids", next)} />
        </Field>
      )}

      {draft.kind === "relation" && (
        <>
          <Field label="Source instance">
            <select value={String(values.source_id ?? "")} onChange={(event) => onUpdateDraft("source_id", event.target.value)}>
              <option value="">Select an instance…</option>
              {instances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </Field>
          <Field label="Relation type">
            <select value={String(values.relation_type_id ?? "")} onChange={(event) => onUpdateDraft("relation_type_id", event.target.value)}>
              <option value="">Select a relation type…</option>
              {relationTypes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </Field>
          <Field label="Target instance">
            <select value={String(values.target_id ?? "")} onChange={(event) => onUpdateDraft("target_id", event.target.value)}>
              <option value="">Select an instance…</option>
              {instances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </Field>
        </>
      )}

      {draft.kind === "attribute_value" && (
        <>
          <Field label="Subject instance">
            <select value={String(values.subject_id ?? "")} onChange={(event) => onUpdateDraft("subject_id", event.target.value)}>
              <option value="">Select an instance…</option>
              {instances.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </Field>
          <Field label="Attribute type">
            <select value={String(values.attribute_type_id ?? "")} onChange={(event) => onUpdateDraft("attribute_type_id", event.target.value)}>
              <option value="">Select an attribute type…</option>
              {attributeTypes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </Field>
          <Field label={`Value (${valueType})`}>
            {valueType === "boolean" ? (
              <select value={String(values.value ?? "")} onChange={(event) => onUpdateDraft("value", event.target.value)}>
                <option value="">Select…</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : (
              <input
                type={valueType === "number" ? "number" : valueType === "date" ? "date" : "text"}
                step={valueType === "number" ? "any" : undefined}
                value={String(values.value ?? "")}
                onChange={(event) => onUpdateDraft("value", event.target.value)}
              />
            )}
          </Field>
        </>
      )}

      {draft.kind === "source_ref" && (
        <>
          <Field label="Label">
            <input value={String(values.label ?? "")} onChange={(event) => onUpdateDraft("label", event.target.value)} />
          </Field>
          <Field label="Locator kind">
            <select value={String(values.locator_kind ?? "url")} onChange={(event) => onUpdateDraft("locator_kind", event.target.value)}>
              {LOCATOR_KINDS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </Field>
          <Field label="Locator" hint="Stored as a reference only; the target is not fetched.">
            <input value={String(values.locator_value ?? "")} onChange={(event) => onUpdateDraft("locator_value", event.target.value)} />
          </Field>
          <Field label="Citation text">
            <textarea rows={3} value={String(values.citation_text ?? "")} onChange={(event) => onUpdateDraft("citation_text", event.target.value)} />
          </Field>
          <Field label="Evidence state">
            <select value={String(values.evidence_state ?? "unverified")} onChange={(event) => onUpdateDraft("evidence_state", event.target.value)}>
              {EVIDENCE_STATES.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </Field>
        </>
      )}

      <Field label="Notes">
        <textarea rows={2} value={String(values.notes ?? "")} onChange={(event) => onUpdateDraft("notes", event.target.value)} />
      </Field>

      <Field label="Source references">
        <MultiSelect value={(values.source_ref_ids as string[]) ?? []} options={sourceRefs} onChange={(next) => onUpdateDraft("source_ref_ids", next)} />
      </Field>

      <Field label="Status" hint="Deprecated objects stay in the graph so references remain valid.">
        <select value={String(values.status ?? "active")} onChange={(event) => onUpdateDraft("status", event.target.value)}>
          {STATUSES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </Field>

      {isAssertion && (
        <p className="fine-print">
          This assertion has its own ID, notes, and source references, so parallel assertions remain
          distinguishable.
        </p>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      <WarningList warnings={warnings} />

      <div className="inspector-actions">
        <button className="primary" onClick={onSave} disabled={busy}>
          {busy ? "Saving…" : draft.mode === "create" ? "Create and save" : "Save changes"}
        </button>
        <button className="ghost" onClick={onCancel} disabled={busy}>Discard</button>
      </div>
    </div>
  );
}

export default function Inspector(props: Props) {
  const {
    state,
    schema,
    selected,
    draft,
    warnings,
    busy,
    error,
    onEdit,
    onUpdateDraft,
    onSave,
    onCancel,
    onDelete,
    onToggleStatus,
    onAddRelation,
    onAddAttribute,
    onSelect,
  } = props;
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setConfirmDelete(false);
  }, [selected?.id]);

  if (draft) {
    return (
      <aside className="inspector" aria-label="Inspector">
        <DraftForm
          draft={draft}
          state={state}
          schema={schema}
          busy={busy}
          error={error}
          warnings={warnings}
          onUpdateDraft={onUpdateDraft}
          onSave={onSave}
          onCancel={onCancel}
        />
      </aside>
    );
  }

  if (!selected) {
    return (
      <aside className="inspector" aria-label="Inspector">
        <div className="inspector-body">
          <p className="eyebrow">Inspector</p>
          <h2>Nothing selected</h2>
          <p className="muted">
            Select an object in the graph, explorer, or table. Schema edges are derived from
            definitions; they are not instance assertions.
          </p>
          <dl className="overview-stats">
            <div>
              <dt>Objects</dt>
              <dd>{state.objects.length}</dd>
            </div>
            <div>
              <dt>Classes</dt>
              <dd>{schema.counts.classes}</dd>
            </div>
            <div>
              <dt>Instances</dt>
              <dd>{state.objects.filter((item) => item.kind === "instance").length}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd>{schema.warnings.length}</dd>
            </div>
          </dl>
          <WarningList warnings={schema.warnings.slice(0, 6)} />
        </div>
      </aside>
    );
  }

  const classes = state.objects.filter((item): item is ClassObject => item.kind === "class");
  const instances = state.objects.filter((item): item is InstanceObject => item.kind === "instance");
  const relations = state.objects.filter((item): item is RelationObject => item.kind === "relation");
  const values = state.objects.filter((item): item is AttributeValueObject => item.kind === "attribute_value");

  const outgoing = selected.kind === "instance" ? relations.filter((item) => item.source_id === selected.id) : [];
  const incoming = selected.kind === "instance" ? relations.filter((item) => item.target_id === selected.id) : [];
  const literals = selected.kind === "instance" ? values.filter((item) => item.subject_id === selected.id) : [];
  const selectedWarnings = warnings.filter((warning) => warning.object_id === selected.id);

  let detail: ReactNode = null;
  if (selected.kind === "class") {
    const classObject = selected as ClassObject;
    const children = classes.filter((item) => item.parent_ids.includes(classObject.id));
    const allowed = descendantClassIds(classes, classObject.id);
    const typed = instances.filter((item) => item.class_ids.some((classId) => allowed.has(classId)));
    detail = (
      <>
        <p className="definition">{classObject.definition || "No definition yet."}</p>
        {classObject.aliases.length > 0 && <p className="muted">Aliases: {classObject.aliases.join(", ")}</p>}
        <dl className="detail-list">
          <div>
            <dt>Parents</dt>
            <dd><IdList ids={classObject.parent_ids} objects={state.objects} onSelect={onSelect} /></dd>
          </div>
          <div>
            <dt>Children</dt>
            <dd><IdList ids={children.map((item) => item.id)} objects={state.objects} onSelect={onSelect} /></dd>
          </div>
          <div>
            <dt>Instances (incl. descendants)</dt>
            <dd>{typed.length}</dd>
          </div>
        </dl>
        {typed.length > 0 && (
          <div className="related-block">
            <p className="eyebrow">Affected instances</p>
            <div className="chip-row">
              {typed.slice(0, 12).map((item) => <Referenced key={item.id} id={item.id} objects={state.objects} onSelect={onSelect} />)}
            </div>
          </div>
        )}
      </>
    );
  } else if (selected.kind === "relation_type") {
    const relationType = selected as RelationTypeObject;
    const usages = relations.filter((item) => item.relation_type_id === relationType.id);
    detail = (
      <>
        <p className="definition">{relationType.definition || "No definition yet."}</p>
        <dl className="detail-list">
          <div><dt>Domain</dt><dd><IdList ids={relationType.domain_ids} objects={state.objects} onSelect={onSelect} /></dd></div>
          <div><dt>Range</dt><dd><IdList ids={relationType.range_ids} objects={state.objects} onSelect={onSelect} /></dd></div>
          <div><dt>Assertions using this type</dt><dd>{usages.length}</dd></div>
        </dl>
        {usages.length > 0 && (
          <div className="related-block">
            <p className="eyebrow">Assertions</p>
            <div className="chip-row">
              {usages.slice(0, 12).map((item) => <Referenced key={item.id} id={item.id} objects={state.objects} onSelect={onSelect} />)}
            </div>
          </div>
        )}
      </>
    );
  } else if (selected.kind === "attribute_type") {
    const attributeType = selected;
    const usages = values.filter((item) => item.attribute_type_id === attributeType.id);
    detail = (
      <>
        <p className="definition">{attributeType.definition || "No definition yet."}</p>
        <dl className="detail-list">
          <div><dt>Domain</dt><dd><IdList ids={attributeType.domain_ids} objects={state.objects} onSelect={onSelect} /></dd></div>
          <div><dt>Value type</dt><dd>{attributeType.value_type}</dd></div>
          <div><dt>Assertions using this type</dt><dd>{usages.length}</dd></div>
        </dl>
      </>
    );
  } else if (selected.kind === "instance") {
    const instance = selected;
    detail = (
      <>
        <p className="definition">{instance.definition || "No definition yet."}</p>
        <dl className="detail-list">
          <div><dt>Classes</dt><dd><IdList ids={instance.class_ids} objects={state.objects} onSelect={onSelect} /></dd></div>
          <div><dt>Outgoing relations</dt><dd>{outgoing.length}</dd></div>
          <div><dt>Incoming relations</dt><dd>{incoming.length}</dd></div>
          <div><dt>Literal values</dt><dd>{literals.length}</dd></div>
        </dl>
        {(outgoing.length > 0 || incoming.length > 0) && (
          <div className="related-block">
            <p className="eyebrow">Relations</p>
            <div className="chip-row">
              {[...outgoing, ...incoming].slice(0, 16).map((item) => <Referenced key={item.id} id={item.id} objects={state.objects} onSelect={onSelect} />)}
            </div>
          </div>
        )}
        {literals.length > 0 && (
          <div className="related-block">
            <p className="eyebrow">Literal values</p>
            <div className="chip-row">
              {literals.map((item) => <Referenced key={item.id} id={item.id} objects={state.objects} onSelect={onSelect} />)}
            </div>
          </div>
        )}
        <div className="inspector-actions wrap">
          <button className="secondary" onClick={() => onAddRelation(instance.id)}>Add relation</button>
          <button className="secondary" onClick={() => onAddAttribute(instance.id)}>Add literal value</button>
        </div>
      </>
    );
  } else if (selected.kind === "relation") {
    const relation = selected;
    detail = (
      <dl className="detail-list">
        <div><dt>Source</dt><dd><Referenced id={relation.source_id} objects={state.objects} onSelect={onSelect} /></dd></div>
        <div><dt>Relation type</dt><dd><Referenced id={relation.relation_type_id} objects={state.objects} onSelect={onSelect} /></dd></div>
        <div><dt>Target</dt><dd><Referenced id={relation.target_id} objects={state.objects} onSelect={onSelect} /></dd></div>
      </dl>
    );
  } else if (selected.kind === "attribute_value") {
    const value = selected;
    detail = (
      <dl className="detail-list">
        <div><dt>Subject</dt><dd><Referenced id={value.subject_id} objects={state.objects} onSelect={onSelect} /></dd></div>
        <div><dt>Attribute type</dt><dd><Referenced id={value.attribute_type_id} objects={state.objects} onSelect={onSelect} /></dd></div>
        <div><dt>Value</dt><dd><code>{String(value.value)}</code></dd></div>
      </dl>
    );
  } else if (selected.kind === "source_ref") {
    const source = selected as SourceRefObject;
    const referencing = state.objects.filter((item) => item.source_ref_ids.includes(source.id));
    detail = (
      <>
        <dl className="detail-list">
          <div><dt>Locator</dt><dd><code>{source.locator.kind}: {source.locator.value}</code></dd></div>
          <div><dt>Evidence</dt><dd>{source.evidence_state.replaceAll("_", " ")}</dd></div>
          <div><dt>Citation</dt><dd>{source.citation_text || "—"}</dd></div>
        </dl>
        <p className="fine-print">
          Exposing a source reference does not verify its contents. The stored evidence state is
          preserved in the read API.
        </p>
        <div className="related-block">
          <p className="eyebrow">Referenced by</p>
          <IdList ids={referencing.map((item) => item.id)} objects={state.objects} onSelect={onSelect} />
        </div>
      </>
    );
  }

  return (
    <aside className="inspector" aria-label="Inspector">
      <div className="inspector-body">
        <div className="inspector-title">
          <span className={`kind-badge kind-${selected.kind}`}>{selected.kind.replaceAll("_", " ")}</span>
          <h2>{objectLabel(selected)}</h2>
        </div>

        {detail}

        {selected.notes && (
          <div className="related-block">
            <p className="eyebrow">Notes</p>
            <p>{selected.notes}</p>
          </div>
        )}

        {selected.source_ref_ids.length > 0 && (
          <div className="related-block">
            <p className="eyebrow">Source references</p>
            <IdList ids={selected.source_ref_ids} objects={state.objects} onSelect={onSelect} />
          </div>
        )}

        {error && <p className="form-error" role="alert">{error}</p>}
        <WarningList warnings={selectedWarnings} />

        <div className="inspector-actions wrap">
          <button className="primary" onClick={onEdit}>Edit</button>
          <button className="secondary" onClick={() => onToggleStatus(selected)}>
            {selected.status === "active" ? "Deprecate" : "Restore"}
          </button>
          {confirmDelete ? (
            <>
              <button className="danger" onClick={() => onDelete(selected)} disabled={busy}>Confirm delete</button>
              <button className="ghost" onClick={() => setConfirmDelete(false)}>Keep</button>
            </>
          ) : (
            <button className="ghost" onClick={() => setConfirmDelete(true)}>Delete…</button>
          )}
        </div>
        <p className="fine-print">
          Deleting a referenced object is rejected with its dependency list unless the same batch
          removes or rewires every reference. There is no implicit cascade.
        </p>
        <Metadata object={selected} />
      </div>
    </aside>
  );
}
