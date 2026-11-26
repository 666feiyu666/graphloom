import cytoscape, {
  Core,
  ElementDefinition,
  EventObject,
} from "cytoscape";
import type { StylesheetCSS } from "cytoscape";
import fcose from "cytoscape-fcose";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import type { ProjectionElement } from "../projections/graph";

(cytoscape as unknown as { use: (extension: unknown) => void }).use(fcose);

export interface GraphCanvasHandle {
  runLayout: () => void;
  fit: () => void;
}

interface Props {
  elements: ProjectionElement[];
  positions: Record<string, { x: number; y: number }>;
  selectedId: string | null;
  linkMode: boolean;
  linkSource: string | null;
  autoLayout: boolean;
  projectionKey: string;
  onSelect: (id: string | null) => void;
  onEdit: (id: string) => void;
  onPositions: (positions: Record<string, { x: number; y: number }>) => void;
  onViewport: (viewport: { zoom: number; pan: { x: number; y: number } }) => void;
  onLinkNode: (id: string) => void;
}

const STYLES = [
  {
    selector: "node",
    style: {
      "background-color": "#dfe5ee",
      "border-width": 1,
      "border-color": "#52606d",
      label: "data(label)",
      color: "#1f2933",
      "font-size": 10,
      "font-family": "Avenir Next, Helvetica Neue, sans-serif",
      "text-valign": "bottom",
      "text-margin-y": 6,
      "text-wrap": "wrap",
      "text-max-width": "140px",
      width: 26,
      height: 26,
      "overlay-opacity": 0,
    },
  },
  {
    selector: 'node[kind = "class"]',
    style: {
      shape: "round-rectangle",
      width: 124,
      height: 44,
      "background-color": "#e6ecf7",
      "border-color": "#3b5b92",
      "border-width": 2,
      "text-valign": "center",
      "text-margin-y": 0,
      "font-weight": 600,
    },
  },
  {
    selector: 'node[kind = "relation_type"]',
    style: {
      shape: "diamond",
      width: 84,
      height: 54,
      "background-color": "#f6e9d5",
      "border-color": "#9a651c",
      "text-valign": "bottom",
      "text-margin-y": 6,
    },
  },
  {
    selector: 'node[kind = "attribute_type"]',
    style: {
      shape: "hexagon",
      width: 96,
      height: 56,
      "background-color": "#e0f0ed",
      "border-color": "#2f6f6a",
      "text-valign": "bottom",
      "text-margin-y": 6,
    },
  },
  {
    selector: 'node[kind = "instance"]',
    style: {
      shape: "ellipse",
      width: 58,
      height: 36,
      "background-color": "#eee7f5",
      "border-color": "#6b4f8a",
      "text-valign": "bottom",
      "text-margin-y": 4,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.4,
      "line-color": "#8b95a5",
      "target-arrow-color": "#8b95a5",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      "curve-style": "bezier",
      label: "data(label)",
      "font-size": 9,
      color: "#52606d",
      "text-background-color": "#f5f2ea",
      "text-background-opacity": 0.92,
      "text-background-padding": "2px",
      "overlay-opacity": 0,
    },
  },
  {
    selector: 'edge[kind = "subclass"]',
    style: {
      "line-color": "#3b5b92",
      "target-arrow-color": "#3b5b92",
    },
  },
  {
    selector: 'edge[kind = "domain"], edge[kind = "range"]',
    style: {
      "line-style": "dashed",
      "line-color": "#9aa5b1",
      "target-arrow-shape": "none",
    },
  },
  {
    selector: 'edge[kind = "relation"]',
    style: {
      width: 2,
      "line-color": "#2f6f6a",
      "target-arrow-color": "#2f6f6a",
    },
  },
  {
    selector: ":selected",
    style: {
      "border-width": 4,
      "border-color": "#b5432f",
      "line-color": "#b5432f",
      "target-arrow-color": "#b5432f",
    },
  },
  {
    selector: ".link-source",
    style: {
      "border-width": 5,
      "border-color": "#d97706",
    },
  },
] as unknown as StylesheetCSS[];

function readPositions(cy: Core): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  cy.nodes().forEach((node) => {
    const position = node.position();
    positions[node.id()] = { x: position.x, y: position.y };
  });
  return positions;
}

function applyPositions(
  cy: Core,
  positions: Record<string, { x: number; y: number }>,
) {
  cy.batch(() => {
    for (const [id, position] of Object.entries(positions)) {
      const node = cy.getElementById(id);
      if (node.nonempty()) node.position(position);
    }
  });
}

const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  {
    elements,
    positions,
    selectedId,
    linkMode,
    linkSource,
    autoLayout,
    projectionKey,
    onSelect,
    onEdit,
    onPositions,
    onViewport,
    onLinkNode,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const didInitialLayout = useRef(false);
  const lastElements = useRef<ProjectionElement[] | null>(null);
  const viewportTimer = useRef<number | null>(null);
  const callbacks = useRef({
    onSelect,
    onEdit,
    onPositions,
    onViewport,
    onLinkNode,
    linkMode,
  });

  useEffect(() => {
    callbacks.current = {
      onSelect,
      onEdit,
      onPositions,
      onViewport,
      onLinkNode,
      linkMode,
    };
  }, [onSelect, onEdit, onPositions, onViewport, onLinkNode, linkMode]);

  function runLayout(animate = true) {
    const cy = cyRef.current;
    if (!cy) return;
    const layout = cy.layout({
      name: "fcose",
      animate,
      animationDuration: 350,
      fit: true,
      padding: 48,
      nodeRepulsion: 9000,
      idealEdgeLength: 130,
      edgeElasticity: 0.45,
      gravity: 0.25,
      numIter: 2500,
      randomize: true,
      quality: "default",
    } as never);
    layout.one("layoutstop", () => {
      callbacks.current.onPositions(readPositions(cy));
    });
    layout.run();
  }

  useImperativeHandle(
    ref,
    () => ({
      runLayout: () => runLayout(true),
      fit: () => {
        const cy = cyRef.current;
        if (cy) cy.fit(undefined, 48);
      },
    }),
    [],
  );

  useEffect(() => {
    if (!containerRef.current || cyRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: STYLES,
      minZoom: 0.15,
      maxZoom: 3,
      boxSelectionEnabled: false,
    });
    cyRef.current = cy;

    cy.on("tap", "node", (event: EventObject) => {
      const id = event.target.id();
      if (callbacks.current.linkMode) callbacks.current.onLinkNode(id);
      else callbacks.current.onSelect(id);
    });
    cy.on("tap", "edge", (event: EventObject) => {
      callbacks.current.onSelect(event.target.id());
    });
    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) callbacks.current.onSelect(null);
    });
    cy.on("dbltap", "node", (event: EventObject) => {
      callbacks.current.onEdit(event.target.id());
    });
    cy.on("dragfree", "node", () => {
      callbacks.current.onPositions(readPositions(cy));
    });
    cy.on("viewport", () => {
      if (viewportTimer.current) window.clearTimeout(viewportTimer.current);
      viewportTimer.current = window.setTimeout(() => {
        callbacks.current.onViewport({ zoom: cy.zoom(), pan: cy.pan() });
      }, 250);
    });

    return () => {
      if (viewportTimer.current) window.clearTimeout(viewportTimer.current);
      cy.destroy();
      cyRef.current = null;
      lastElements.current = null;
      didInitialLayout.current = false;
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      cyRef.current?.resize();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    didInitialLayout.current = false;
  }, [projectionKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const ensureLayout = () => {
      if (!cy.nodes().length) return;
      if (Object.keys(positions).length > 0) return;
      const unique = new Set(
        cy.nodes().map(
          (node) => `${Math.round(node.position("x"))},${Math.round(node.position("y"))}`,
        ),
      ).size;
      if (unique > 1) return;
      // Built-in cose is synchronous, so a collapsed first view self-heals.
      cy.resize();
      cy.layout({ name: "cose", animate: false, fit: true, padding: 48 } as never).run();
      callbacks.current.onPositions(readPositions(cy));
    };

    if (lastElements.current !== elements) {
      const firstLoad = lastElements.current === null;
      const viewport = { zoom: cy.zoom(), pan: cy.pan() };
      cy.batch(() => {
        cy.elements().remove();
        if (elements.length) cy.add(elements as ElementDefinition[]);
      });
      lastElements.current = elements;
      applyPositions(cy, positions);
      if (firstLoad && Object.keys(positions).length > 0) {
        cy.fit(undefined, 48);
      } else if (!firstLoad) {
        cy.zoom(viewport.zoom);
        cy.pan(viewport.pan);
      }
    } else {
      applyPositions(cy, positions);
    }
    ensureLayout();
  }, [elements, positions]);

  useEffect(() => {
    didInitialLayout.current = false;
  }, [projectionKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().unselect();
    if (selectedId) {
      const target = cy.getElementById(selectedId);
      if (target.nonempty()) target.select();
    }
  }, [selectedId, elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("link-source");
    if (linkSource) {
      const target = cy.getElementById(linkSource);
      if (target.nonempty()) target.addClass("link-source");
    }
  }, [linkSource, elements]);

  return (
    <section className="graph-view" aria-label="Graph view">
      <div className="graph-canvas" ref={containerRef} />
      {elements.length === 0 && (
        <div className="graph-empty">
          <h2>No objects in this projection</h2>
          <p>
            Create a class, a relation type, and an instance from the explorer, or switch to
            the table view.
          </p>
        </div>
      )}
      {linkMode && (
        <div className="canvas-hint">
          {linkSource
            ? "Now select the target instance."
            : "Select the source instance for the new relation."}
        </div>
      )}
    </section>
  );
});

export default GraphCanvas;
