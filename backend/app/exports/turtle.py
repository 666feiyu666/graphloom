from __future__ import annotations

from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from app.domain.graph import object_map
from app.domain.objects import (
    AttributeTypeObject,
    AttributeValueObject,
    ClassObject,
    InstanceObject,
    RelationObject,
    RelationTypeObject,
    SourceRefObject,
)

GL = Namespace("urn:graphloom:vocab#")
OBJECT_NS = "urn:graphloom:object:"
PROJECT_NS = "urn:graphloom:project:"

EXPORT_WARNING = (
    "Graphloom export warning: advisory domain/range lists are serialized as "
    "Graphloom metadata (gl:domain and gl:range), not as OWL/RDFS restrictions. "
    "Multiple listed classes mean 'any listed class or descendant' in the application; "
    "that semantics is not represented as several RDF domain axioms. Duplicate base "
    "triples may collapse, while reified assertion records preserve assertion identity. "
    "Native JSON remains the exact round-trip format. This export does not verify an "
    "assertion or a source."
)


def object_iri(project_id: str, object_id: str) -> URIRef:
    return URIRef(f"{OBJECT_NS}{project_id}:{object_id}")


def project_iri(project_id: str) -> URIRef:
    return URIRef(f"{PROJECT_NS}{project_id}")


def _literal_for_value(value: Any, value_type: str) -> Any:
    if value_type == "number":
        if isinstance(value, bool):
            return Literal(str(value), datatype=XSD.boolean)
        if isinstance(value, int):
            return Literal(value, datatype=XSD.integer)
        try:
            return Literal(float(value), datatype=XSD.double)
        except (TypeError, ValueError):
            return Literal(str(value))
    if value_type == "boolean":
        if isinstance(value, str):
            parsed = value.strip().lower() == "true"
        else:
            parsed = bool(value)
        return Literal(parsed, datatype=XSD.boolean)
    if value_type == "date":
        return Literal(str(value), datatype=XSD.date)
    if value_type == "uri":
        return URIRef(str(value))
    return Literal("" if value is None else str(value), datatype=XSD.string)


def _common(graph: Graph, iri: URIRef, obj, project_node: URIRef) -> None:
    graph.add((iri, GL.objectId, Literal(str(obj.id))))
    graph.add((iri, GL.kind, Literal(obj.kind)))
    graph.add((iri, GL.project, project_node))
    graph.add((iri, GL.reviewStatus, Literal(obj.review_status)))
    graph.add((iri, GL.lifecycle, Literal(obj.lifecycle)))
    graph.add((iri, GL.origin, Literal(obj.origin)))
    graph.add((iri, GL.createdBy, Literal(obj.created_by)))
    graph.add((iri, GL.updatedBy, Literal(obj.updated_by)))
    if obj.notes:
        graph.add((iri, GL.notes, Literal(obj.notes)))
    for source_ref_id in obj.source_ref_ids:
        graph.add(
            (
                iri,
                GL.sourceReference,
                object_iri(str(obj.project_id), str(source_ref_id)),
            )
        )


def _named(graph: Graph, iri: URIRef, obj) -> None:
    graph.add((iri, RDFS.label, Literal(obj.label)))
    if obj.definition:
        graph.add((iri, RDFS.comment, Literal(obj.definition)))
    for alias in obj.aliases:
        graph.add((iri, SKOS.altLabel, Literal(alias)))


def build_turtle_export(project, state) -> str:
    graph = Graph()
    graph.bind("gl", GL)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("skos", SKOS)
    graph.bind("xsd", XSD)

    project_node = project_iri(project.id)
    graph.add((project_node, RDF.type, GL.Project))
    graph.add((project_node, RDFS.label, Literal(project.name)))
    if project.description:
        graph.add((project_node, RDFS.comment, Literal(project.description)))
    graph.add((project_node, GL.revision, Literal(state.revision)))
    graph.add((project_node, GL.exportWarning, Literal(EXPORT_WARNING)))

    index = object_map(state)

    for obj in state.objects:
        iri = object_iri(project.id, str(obj.id))
        _common(graph, iri, obj, project_node)

        if isinstance(obj, ClassObject):
            graph.add((iri, RDF.type, OWL.Class))
            _named(graph, iri, obj)
            for parent_id in obj.parent_ids:
                graph.add(
                    (iri, RDFS.subClassOf, object_iri(project.id, str(parent_id)))
                )

        elif isinstance(obj, RelationTypeObject):
            graph.add((iri, RDF.type, OWL.ObjectProperty))
            _named(graph, iri, obj)
            for domain_id in obj.domain_ids:
                graph.add((iri, GL.domain, object_iri(project.id, str(domain_id))))
            for range_id in obj.range_ids:
                graph.add((iri, GL.range, object_iri(project.id, str(range_id))))

        elif isinstance(obj, AttributeTypeObject):
            graph.add((iri, RDF.type, OWL.DatatypeProperty))
            _named(graph, iri, obj)
            graph.add((iri, GL.valueType, Literal(obj.value_type)))
            for domain_id in obj.domain_ids:
                graph.add((iri, GL.domain, object_iri(project.id, str(domain_id))))

        elif isinstance(obj, InstanceObject):
            _named(graph, iri, obj)
            if obj.class_ids:
                for class_id in obj.class_ids:
                    graph.add(
                        (iri, RDF.type, object_iri(project.id, str(class_id)))
                    )
            else:
                graph.add((iri, RDF.type, GL.Instance))

        elif isinstance(obj, RelationObject):
            source = object_iri(project.id, str(obj.source_id))
            predicate = object_iri(project.id, str(obj.relation_type_id))
            target = object_iri(project.id, str(obj.target_id))
            graph.add((source, predicate, target))
            graph.add((iri, RDF.type, RDF.Statement))
            graph.add((iri, RDF.type, GL.RelationAssertion))
            graph.add((iri, RDF.subject, source))
            graph.add((iri, RDF.predicate, predicate))
            graph.add((iri, RDF.object, target))
            graph.add((source, GL.assertion, iri))

        elif isinstance(obj, AttributeValueObject):
            subject = object_iri(project.id, str(obj.subject_id))
            predicate = object_iri(project.id, str(obj.attribute_type_id))
            attribute_type = index.get(str(obj.attribute_type_id))
            value_type = (
                attribute_type.value_type
                if isinstance(attribute_type, AttributeTypeObject)
                else "string"
            )
            value = _literal_for_value(obj.value, value_type)
            graph.add((subject, predicate, value))
            graph.add((iri, RDF.type, RDF.Statement))
            graph.add((iri, RDF.type, GL.AttributeAssertion))
            graph.add((iri, RDF.subject, subject))
            graph.add((iri, RDF.predicate, predicate))
            graph.add((iri, RDF.object, value))
            graph.add((subject, GL.assertion, iri))

        elif isinstance(obj, SourceRefObject):
            graph.add((iri, RDF.type, GL.SourceReference))
            graph.add((iri, RDFS.label, Literal(obj.label)))
            graph.add((iri, GL.locatorKind, Literal(obj.locator.kind)))
            graph.add((iri, GL.locatorValue, Literal(obj.locator.value)))
            if obj.citation_text:
                graph.add((iri, GL.citationText, Literal(obj.citation_text)))
            graph.add((iri, GL.evidenceState, Literal(obj.evidence_state)))

    return graph.serialize(format="turtle")
