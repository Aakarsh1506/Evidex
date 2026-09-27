import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { fetchCriminalNetwork } from '../api/criminals';
import './RelationGraph.css';
import { useTranslation } from '../i18n';

// Per-kind palette: a saturated fill plus a paler halo used for the border,
// mirroring the soft-glow node treatment common to modern network charts.
const KIND_STYLE = {
  Organization: { label: 'Organization', fill: '#c47b9a', halo: '#f5bbd2', shape: 'round-rectangle' },
  Vehicle: { label: 'Vehicle', fill: '#b18c60', halo: '#e8c799', shape: 'rectangle' },
  PhoneNumber: { label: 'Phone number', fill: '#7891c9', halo: '#b6ccff', shape: 'ellipse' },
  Person: { label: 'Person', fill: '#d9a94e', halo: '#f6d98b', shape: 'ellipse' },
  Case: { label: 'Case', fill: '#4e8fc7', halo: '#a8d4ff', shape: 'round-rectangle' },
  Location: { label: 'Location', fill: '#3fa893', halo: '#92e8d2', shape: 'diamond' },
  CrimeType: { label: 'Crime type', fill: '#9678c9', halo: '#d3bff2', shape: 'hexagon' },
};
const ROOT_STYLE = { fill: '#d9614f', halo: '#ffb199' };
const DEFAULT_STYLE = { fill: '#8f9bb0', halo: '#c7cfdc', shape: 'ellipse' };

const stylesheet = [
  { selector: 'node', style: {
    label: 'data(displayLabel)', width: 32, height: 32, shape: 'ellipse',
    'background-color': DEFAULT_STYLE.fill, 'border-width': 2.5, 'border-color': DEFAULT_STYLE.halo,
    'border-opacity': 0.9, 'corner-radius': 10,
    color: '#eef2f8', 'font-family': 'IBM Plex Sans, sans-serif', 'font-size': 11, 'font-weight': 500,
    'text-valign': 'bottom', 'text-halign': 'center', 'text-margin-y': 9, 'text-wrap': 'wrap', 'text-max-width': 110,
    'text-background-color': '#0d1219', 'text-background-opacity': 0.88, 'text-background-shape': 'roundrectangle',
    'text-background-padding': 4,
    'overlay-opacity': 0, 'overlay-color': DEFAULT_STYLE.halo, 'overlay-padding': 6, 'overlay-shape': 'ellipse',
    'transition-property': 'overlay-opacity, overlay-padding, border-width, background-color, border-color',
    'transition-duration': '160ms',
  } },
  ...Object.entries(KIND_STYLE).map(([kind, k]) => ({
    selector: `node[kind = "${kind}"]`,
    style: { shape: k.shape, 'background-color': k.fill, 'border-color': k.halo, 'overlay-color': k.halo },
  })),
  { selector: 'node[kind = "Person"]', style: { width: 40, height: 40 } },
  { selector: 'node[kind = "Location"]', style: { width: 36, height: 36 } },
  { selector: 'node[kind = "Case"], node[kind = "CrimeType"]', style: { width: 40, height: 34, padding: 4 } },
  { selector: 'node[depth = 0]', style: {
    width: 62, height: 62, 'background-color': ROOT_STYLE.fill, 'border-color': ROOT_STYLE.halo,
    'overlay-color': ROOT_STYLE.halo, 'border-width': 3.5,
    'font-size': 13, 'font-weight': 700, color: '#fff5ea', 'text-margin-y': 14, 'z-index': 20,
    'overlay-opacity': 0.14, 'overlay-padding': 8,
  } },
  { selector: 'edge', style: {
    'curve-style': 'bezier', 'control-point-step-size': 42, width: 1.4, 'line-cap': 'round',
    'line-color': '#5c6b82', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#5c6b82',
    'arrow-scale': 0.65, opacity: 0.55, label: '', 'font-size': 9, color: '#e7d3ab',
    'text-rotation': 'autorotate', 'text-background-color': '#0d1219', 'text-background-opacity': 0.92,
    'text-background-padding': 4, 'text-background-shape': 'roundrectangle', 'overlay-opacity': 0,
    'transition-property': 'opacity, width, line-color, target-arrow-color', 'transition-duration': '160ms',
  } },
  { selector: 'edge[count > 1]', style: { width: 'mapData(count, 2, 6, 2, 3.4)', opacity: 0.7 } },
  { selector: 'edge.bidirectional', style: { 'source-arrow-shape': 'triangle', 'source-arrow-color': '#5c6b82' } },
  { selector: 'node:selected, node.hovered', style: {
    'border-width': 3.5, 'overlay-opacity': 0.22, 'overlay-padding': 7,
  } },
  { selector: 'edge.focused, edge:selected, edge.hovered', style: {
    width: 2.6, 'line-color': '#e0b072', 'target-arrow-color': '#e0b072', 'source-arrow-color': '#e0b072',
    opacity: 1, 'z-index': 15,
  } },
  { selector: 'node.focused', style: { 'z-index': 12 } },
  { selector: '.muted', style: { opacity: 0.12 } },
];

// Draw one line per pair of nodes. Several recorded relationships between the same two
// records (e.g. MENTIONED_IN and SUSPECT_IN) are kept on the line and listed when selected.
function mergeEdges(edges) {
  const pairs = new Map();
  for (const edge of edges) {
    const key = [edge.source, edge.target].sort().join('\u0000');
    if (!pairs.has(key)) pairs.set(key, []);
    pairs.get(key).push(edge);
  }
  return [...pairs.values()].map((group) => {
    const [first] = group;
    const labels = [...new Set(group.map((edge) => edge.label).filter(Boolean))];
    const bidirectional = group.some((edge) => edge.source !== first.source);
    return {
      ...first,
      label: labels.join(' · '),
      count: group.length,
      bidirectional,
      relationships: group,
    };
  });
}

// Scatter starting positions so the force simulation can form natural clusters.
// Start the selected person near the center; every node remains draggable.
function networkElements(network, edges) {
  const spread = Math.max(300, Math.sqrt(network.nodes.length) * 140);
  const roots = network.nodes.filter((node) => node.depth === 0);
  return [
    ...network.nodes.map((node) => {
      const root = node.depth === 0;
      return {
        data: node,
        position: root ? { x: (roots.indexOf(node) - (roots.length - 1) / 2) * 280, y: 0 } : { x: (Math.random() - 0.5) * spread, y: (Math.random() - 0.5) * spread },
        grabbable: true,
      };
    }),
    ...edges.map((edge) => ({ data: edge, classes: edge.bidirectional ? 'bidirectional' : '' })),
  ];
}

function fitAroundPerson(cy) {
  // Fit the whole graph snugly into the frame. (A symmetric fit around the
  // selected person was tried here, but it wastes space whenever that
  // person sits near one edge of the graph instead of its middle.)
  cy.fit(cy.elements(), 60);
}

export default function RelationGraph({ mainCriminal, network: suppliedNetwork, onNodeClick, onSelectionChange, height = 480 }) {
  const { t } = useTranslation();
  const [result, setResult] = useState(null);
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState(null);
  const container = useRef(null);
  const cyRef = useRef(null);
  const network = suppliedNetwork ?? (result?.id === mainCriminal.id ? result.data : null);
  const error = suppliedNetwork ? '' : result?.id === mainCriminal.id ? result.error : '';
  const edges = useMemo(() => (network ? mergeEdges(network.edges) : []), [network]);

  useEffect(() => {
    if (suppliedNetwork) return;
    const controller = new AbortController();
    fetchCriminalNetwork(mainCriminal.id, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setResult({ id: mainCriminal.id, data }); })
      .catch((err) => { if (!controller.signal.aborted) setResult({ id: mainCriminal.id, error: err.message }); });
    return () => controller.abort();
  }, [mainCriminal.id, retry, suppliedNetwork]);

  useEffect(() => {
    if (!network || !container.current) return;
    const cy = cytoscape({
      container: container.current, elements: networkElements(network, edges),
      style: stylesheet, layout: { name: 'preset', fit: false },
      minZoom: 0.05, maxZoom: 4, wheelSensitivity: 0.2, selectionType: 'single',
    });
    cyRef.current = cy;
    fitAroundPerson(cy);
    const forceLayout = cy.layout({
      name: 'cose', randomize: false, fit: false,
      animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches && network.nodes.length < 150,
      nodeRepulsion: () => 24000, idealEdgeLength: () => 180, componentSpacing: 180,
      nodeDimensionsIncludeLabels: true, nodeOverlap: 20, gravity: 0.4,
      stop: () => fitAroundPerson(cy),
    });
    forceLayout.run();
    cy.on('grab', 'node', () => forceLayout.stop());
    cy.on('select', 'node, edge', ({ target }) => {
      setSelected(target.data());
      cy.elements().removeClass('muted focused');
      const focus = target.isNode() ? target.closedNeighborhood() : target.union(target.connectedNodes());
      focus.addClass('focused');
      cy.elements().difference(focus).addClass('muted');
    });
    cy.on('unselect', 'node, edge', () => {
      if (cy.$(':selected').empty()) {
        setSelected(null);
        cy.elements().removeClass('muted focused');
      }
    });
    cy.on('tap', (event) => {
      if (event.target === cy) {
        cy.elements().unselect().removeClass('muted focused');
        setSelected(null);
      }
    });
    cy.on('mouseover', 'node, edge', ({ target }) => { target.addClass('hovered'); cy.container().style.cursor = 'pointer'; });
    cy.on('mouseout', 'node, edge', ({ target }) => { target.removeClass('hovered'); cy.container().style.cursor = 'grab'; });
    const observer = new ResizeObserver(() => { cy.resize(); fitAroundPerson(cy); });
    observer.observe(container.current);
    return () => { observer.disconnect(); forceLayout.stop(); cy.destroy(); cyRef.current = null; };
  }, [network, edges]);

  function inspect(id) {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().unselect().removeClass('muted focused');
    setSelected(null);
    if (id) cy.getElementById(id).select();
  }
  function zoom(factor) {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * factor)), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }

  const activeSelection = network && selected && [...network.nodes, ...edges].find((item) => item.id === selected.id);

  useEffect(() => {
    onSelectionChange?.(activeSelection ? {
      type: activeSelection.kind ? 'node' : 'edge',
      id: activeSelection.id,
      personId: activeSelection.originPersonId || mainCriminal.id,
      label: activeSelection.kind ? activeSelection.label : `${network.nodes.find((node) => node.id === activeSelection.source)?.label || 'Record'} ${activeSelection.bidirectional ? '↔' : '→'} ${activeSelection.label} ${activeSelection.bidirectional ? '↔' : '→'} ${network.nodes.find((node) => node.id === activeSelection.target)?.label || 'Record'}`,
    } : null);
  }, [activeSelection, network, onSelectionChange, mainCriminal.id]);

  // Legend only lists the node kinds actually present in this network.
  const legendKinds = useMemo(() => {
    if (!network) return [];
    const present = new Set(network.nodes.map((node) => node.kind).filter(Boolean));
    return Object.keys(KIND_STYLE).filter((kind) => present.has(kind));
  }, [network]);

  return <div className="relation-graph">
    <div className="relation-graph__toolbar">
      <div role="group" aria-label={t("graphControls")} className="relation-graph__controls">
        <button className="rg-btn" type="button" aria-label={t("zoomIn")} disabled={!network} onClick={() => zoom(1.3)}>+</button>
        <button className="rg-btn" type="button" aria-label={t("zoomOut")} disabled={!network} onClick={() => zoom(1 / 1.3)}>−</button>
        <button className="rg-btn" type="button" disabled={!network} onClick={() => { if (cyRef.current) fitAroundPerson(cyRef.current); }}>{t("fit")}</button>
      </div>
    </div>

    {legendKinds.length > 0 && <div className="relation-graph__legend" aria-hidden="true">
      <span className="rg-legend-item"><span className="rg-legend-swatch" style={{ background: ROOT_STYLE.fill }} />{t("selectedPerson")}</span>
      {legendKinds.map((kind) => (
        <span key={kind} className="rg-legend-item">
          <span className="rg-legend-swatch" style={{ background: KIND_STYLE[kind].fill }} />{KIND_STYLE[kind].label}
        </span>
      ))}
    </div>}

    {error ? <p role="alert" className="relation-graph__status">{error} <button className="rg-btn" type="button" onClick={() => { setResult(null); setSelected(null); setRetry((value) => value + 1); }}>{t("retry")}</button></p>
      : !network ? <p role="status" className="relation-graph__status">{t("loadingRecords")}</p>
      : <>
        <div className="relation-graph__canvas-wrap">
          <div ref={container} className="relation-graph__canvas" style={{ height }} role="img" aria-label={`Relationship graph centered on ${mainCriminal.name}. Use the selector below to inspect nodes and links.`} />
        </div>
        {network.edges.length === 0 && <p className="relation-graph__empty">{t("noRelationshipsPerson")}</p>}
        {network.truncated && <p role="status" className="relation-graph__truncated">Showing the first {network.pathLimit.toLocaleString()} paths; some connections are omitted.</p>}

        <div aria-live="polite">{activeSelection && <div className="relation-graph__panel">
          <span className="relation-graph__panel-title">{activeSelection.label}</span>
          <span className="relation-graph__panel-meta">{activeSelection.kind ? `${activeSelection.kind} · ${activeSelection.depth === 0 ? t("selectedPerson") : `${activeSelection.depth} ${t("graphStepsAway")}`}` : t("recordedRelationship")}</span>
          {activeSelection.personId && <span className="relation-graph__panel-meta">{activeSelection.personId} · {activeSelection.city || t("cityUnavailable")}</span>}
          {(activeSelection.relationships ?? [activeSelection]).map((relation) => <div className="relation-graph__panel-relation" key={relation.id}>
            {activeSelection.count > 1 && <span className="relation-graph__panel-meta relation-graph__panel-label">{relation.label}</span>}
            {relation.reason && <span className="relation-graph__panel-meta">{relation.reason}</span>}
            {relation.evidence && <span className="relation-graph__panel-meta">{t("evidenceLabel")}: {relation.evidence}</span>}
            {relation.reviewStatus && <span className="relation-graph__panel-meta">{t("reviewLabel")}: {relation.reviewStatus}</span>}
            {relation.provenance && <span className="relation-graph__panel-meta">{t("sourceLabel")}: {relation.provenance}</span>}
          </div>)}
          <div className="relation-graph__panel-actions">
            {activeSelection.personId && activeSelection.personId !== String(mainCriminal.id) && onNodeClick && <button className="rg-btn" type="button" onClick={() => onNodeClick(activeSelection.personId)}>{t("openProfile")}</button>}
            <button className="rg-btn" type="button" onClick={() => inspect('')}>{t("clearSelection") || "Clear selection"}</button>
          </div>
        </div>}</div>
      </>}
  </div>;
}
