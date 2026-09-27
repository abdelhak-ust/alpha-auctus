// Run with: npm test  (node:test through tsx — see package.json).
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';
import { buildImpactGraph } from './impactGraph.js';
import type { Decision, Feature, Item, VerdictDetail } from '../types.js';

const item = (id: number, extra: Partial<Item> = {}): Item => ({
  id,
  title: `Item ${id}`,
  description: '',
  status: 'inbox',
  priority: 'P2',
  assignee: 'AM',
  area: 'general',
  created_at: '2026-01-01T00:00:00.000Z',
  source: null,
  verdict: null,
  ...extra,
});

describe('buildImpactGraph', () => {
  test('two cards in the same area share one area node and two depends-on edges', () => {
    const graph = buildImpactGraph({
      items: [item(1, { area: 'Auth' }), item(2, { title: 'Billing Auth', area: 'Auth' })],
      decisions: [],
      features: [],
    });

    const areas = graph.nodes.filter(n => n.type === 'area');
    assert.equal(areas.length, 1);
    assert.equal(areas[0].id, 'area-auth');

    const deps = graph.edges.filter(e => e.type === 'depends-on');
    assert.equal(deps.length, 2);
    assert.ok(deps.some(e => e.source === 'item-1' && e.target === 'area-auth'));
    assert.ok(deps.some(e => e.source === 'item-2' && e.target === 'area-auth'));
  });

  test('a duplicate verdict creates a duplicate edge to the candidate item', () => {
    const verdict: VerdictDetail = {
      type: 'duplicate',
      confidence: 91,
      message: 'Overlaps Item 2',
      candidates: [
        { id: '#2', type: 'item', title: 'Item 2', reason: 'same export', confidence: 91 },
      ],
    };
    const graph = buildImpactGraph({
      items: [item(1, { title: 'CSV Button', verdict }), item(2, { title: 'CSV Reporter' })],
      decisions: [],
      features: [],
    });

    const dups = graph.edges.filter(e => e.type === 'duplicate');
    assert.equal(dups.length, 1);
    assert.equal(dups[0].source, 'item-1');
    assert.equal(dups[0].target, 'item-2');
  });

  test('empty items produce no demo SSO/CSV nodes', () => {
    const graph = buildImpactGraph({ items: [], decisions: [], features: [] });
    assert.equal(graph.nodes.length, 0);
    assert.equal(graph.edges.length, 0);
    const blob = graph.nodes.map(n => `${n.id} ${n.label}`).join(' ').toLowerCase();
    assert.equal(/sso|csv|node-142|dec-4|redirection/.test(blob), false);
  });

  test('does not invent a decision node from a dangling verdict citation', () => {
    const graph = buildImpactGraph({
      items: [item(10, {
        verdict: {
          type: 'conflict',
          confidence: 80,
          message: 'Conflicts with a missing decision',
          candidates: [],
          citation: { id: 'decision-4', type: 'decision', title: 'Rely on IdP', snippet: 'avoid custom SSO' },
        },
      })],
      decisions: [] as Decision[],
      features: [] as Feature[],
    });
    assert.equal(graph.nodes.some(n => n.id === 'decision-4' || n.type === 'decision'), false);
    assert.equal(graph.edges.some(e => e.source.startsWith('decision-') || e.target.startsWith('decision-')), false);
  });
});
