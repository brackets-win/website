import { useCallback, useEffect, useMemo, useState } from 'react';

import { BracketFill } from '../bracket/BracketFill';
import {
  ApiError,
  adminCreateBracket,
  adminDeleteBracket,
  adminListBracketTemplates,
  adminListContestants,
  adminUpdateBracket,
  adminUpdateBracketStages,
  getBracket,
  listBrackets,
  type BracketStageInfo,
  type BracketStructureType,
  type BracketSummary,
  type BracketTemplateSummary,
  type ContestantCatalog,
} from '../../utils/api';

import { AdminBackBar } from './AdminBackBar';
import { AdminNumberInput } from './AdminNumberInput';
import { BracketStageEditor } from './BracketStageEditor';
import {
  buildStructureConfig,
  metadataToText,
  parseMetadataJson,
  stageToAdminPatch,
} from './bracketAdminHelpers';
import { AdminCatalogToolbar } from './AdminCatalogToolbar';
import { IconPencil, IconTrash } from './AdminIcons';
import { DeleteConfirmDialog } from './DeleteConfirmDialog';
import {
  startDeleteTarget,
  type AdminDeleteTarget,
} from './deleteDialogHelpers';
import './admin-shared.css';

type AssignRow = { seed: string; contestant_id: string };

type BracketTemplateChoice = number | 'custom';

function structureKindLabel(kind: BracketStructureType): string {
  return kind === 'GROUP_KNOCKOUT'
    ? 'Group stage + knockout'
    : 'Single elimination';
}

function applyBracketTemplate(
  tpl: BracketTemplateSummary,
  setStructureKind: (k: BracketStructureType) => void,
  setBN: (n: number) => void,
) {
  setStructureKind(tpl.template_type);
  if (tpl.default_number_of_contestants != null) {
    setBN(tpl.default_number_of_contestants);
  }
}

function buildAssignRows(
  count: number,
  prev: AssignRow[],
): AssignRow[] {
  const rows: AssignRow[] = [];
  for (let i = 0; i < count; i++) {
    rows.push({
      seed: String(i + 1),
      contestant_id: prev[i]?.contestant_id ?? '',
    });
  }
  return rows;
}

export function BracketsAdmin() {
  const [brackets, setBrackets] = useState<BracketSummary[]>([]);
  const [bracketTemplates, setBracketTemplates] = useState<
    BracketTemplateSummary[]
  >([]);
  const [contestants, setContestants] = useState<ContestantCatalog[]>([]);
  const [loadErr, setLoadErr] = useState('');

  const [bTemplateId, setBTemplateId] = useState<BracketTemplateChoice | ''>(
    '',
  );
  const [structureKind, setStructureKind] =
    useState<BracketStructureType>('SINGLE_ELIM');
  const [bIdentifier, setBIdentifier] = useState('');
  const [bName, setBName] = useState('');
  const [bDesc, setBDesc] = useState('');
  const [bN, setBN] = useState(8);
  const [bThird, setBThird] = useState(false);
  const [bRand, setBRand] = useState(false);
  const [bShowSeeds, setBShowSeeds] = useState(true);
  const [bMetadata, setBMetadata] = useState('');
  const [bNumGroups, setBNumGroups] = useState('');
  const [bMatchesPer, setBMatchesPer] = useState(3);
  const [bQualify, setBQualify] = useState(2);
  const [bPtWin, setBPtWin] = useState(3);
  const [bPtTie, setBPtTie] = useState(1);
  const [bPtLoss, setBPtLoss] = useState(0);
  const [bTiesAllowed, setBTiesAllowed] = useState(true);
  const [bGroupExactPts, setBGroupExactPts] = useState(1);
  const [bGroupAdvancerPts, setBGroupAdvancerPts] = useState(0);
  const [bGroupRandom, setBGroupRandom] = useState(false);
  const [bChampionPts, setBChampionPts] = useState(0);
  const [bThirdPlacePts, setBThirdPlacePts] = useState(0);
  const [bKoLegs, setBKoLegs] = useState(1);
  const [bKoET, setBKoET] = useState(true);
  const [bKoPK, setBKoPK] = useState(true);
  const [bKoPickPts, setBKoPickPts] = useState(1);
  const [bKoRandom, setBKoRandom] = useState(false);
  const [bImage, setBImage] = useState<File | null>(null);
  const [bImagePreview, setBImagePreview] = useState<string | null>(null);
  const [assignRows, setAssignRows] = useState<AssignRow[]>(() =>
    buildAssignRows(8, []),
  );
  const [assignSearch, setAssignSearch] = useState('');
  const [view, setView] = useState<'list' | 'create' | 'edit' | 'master'>('list');
  const [listSearch, setListSearch] = useState('');
  const [pageMsg, setPageMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(
    null,
  );
  const [createBusy, setCreateBusy] = useState(false);
  const [fillMasterUbId, setFillMasterUbId] = useState<number | null>(null);
  const [fillBracketName, setFillBracketName] = useState('');
  const [editBracketId, setEditBracketId] = useState<number | null>(null);
  const [editIdentifier, setEditIdentifier] = useState('');
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editImage, setEditImage] = useState<File | null>(null);
  const [editImagePreview, setEditImagePreview] = useState<string | null>(null);
  const [editExistingImageUrl, setEditExistingImageUrl] = useState<string | null>(
    null,
  );
  const [editShowSeeds, setEditShowSeeds] = useState(true);
  const [editRand, setEditRand] = useState(false);
  const [editThird, setEditThird] = useState(false);
  const [editChampionPts, setEditChampionPts] = useState(0);
  const [editThirdPlacePts, setEditThirdPlacePts] = useState(0);
  const [editMetadata, setEditMetadata] = useState('');
  const [editStages, setEditStages] = useState<BracketStageInfo[]>([]);
  const firstKnockoutStageId = useMemo(() => {
    const ko = editStages
      .filter(
        (s) => s.stage_type === 'KNOCKOUT' && !s.knockout?.is_third_place,
      )
      .sort((a, b) => a.order - b.order);
    return ko[0]?.id ?? null;
  }, [editStages]);
  const editHasGroupStage = useMemo(
    () => editStages.some((s) => s.stage_type === 'GROUP'),
    [editStages],
  );
  const [editLoadBusy, setEditLoadBusy] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AdminDeleteTarget | null>(
    null,
  );
  const [deleteBusy, setDeleteBusy] = useState(false);

  const selectedTemplate = useMemo(() => {
    if (bTemplateId === '' || bTemplateId === 'custom') return null;
    return bracketTemplates.find((t) => t.id === bTemplateId) ?? null;
  }, [bTemplateId, bracketTemplates]);

  const reload = useCallback(async () => {
    setLoadErr('');
    const errors: string[] = [];

    const [contestantsResult, bracketsResult, templatesResult] =
      await Promise.allSettled([
        adminListContestants(),
        listBrackets(),
        adminListBracketTemplates(),
      ]);

    if (contestantsResult.status === 'fulfilled') {
      setContestants(contestantsResult.value.contestants);
    } else {
      errors.push(
        contestantsResult.reason instanceof ApiError
          ? contestantsResult.reason.message
          : 'Unable to load contestants.',
      );
    }

    if (bracketsResult.status === 'fulfilled') {
      setBrackets(bracketsResult.value.brackets);
    } else {
      errors.push(
        bracketsResult.reason instanceof ApiError
          ? bracketsResult.reason.message
          : 'Unable to load brackets.',
      );
    }

    if (templatesResult.status === 'fulfilled') {
      const templates = templatesResult.value.templates;
      setBracketTemplates(templates);
      setBTemplateId((prev) => {
        if (prev === 'custom') return prev;
        if (typeof prev === 'number' && templates.some((t) => t.id === prev)) {
          return prev;
        }
        return templates[0]?.id ?? 'custom';
      });
    } else {
      setBracketTemplates([]);
      errors.push(
        templatesResult.reason instanceof ApiError
          ? templatesResult.reason.message
          : 'Unable to load bracket templates.',
      );
    }

    if (errors.length > 0) {
      setLoadErr(errors[0]);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    setAssignRows((prev) => buildAssignRows(bN, prev));
  }, [bN]);

  useEffect(() => {
    if (!bImage) {
      setBImagePreview(null);
      return;
    }
    const url = URL.createObjectURL(bImage);
    setBImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [bImage]);

  useEffect(() => {
    if (!editImage) {
      setEditImagePreview(editExistingImageUrl);
      return;
    }
    const url = URL.createObjectURL(editImage);
    setEditImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [editImage, editExistingImageUrl]);

  const isSingleElim = structureKind === 'SINGLE_ELIM';

  const contestantOptions = useMemo(() => {
    const q = assignSearch.trim().toLowerCase();
    if (!q) return contestants;
    return contestants.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.identifier.toLowerCase().includes(q),
    );
  }, [contestants, assignSearch]);

  const filteredBrackets = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    if (!q) return brackets;
    return brackets.filter(
      (b) =>
        b.name.toLowerCase().includes(q) ||
        b.identifier.toLowerCase().includes(q),
    );
  }, [brackets, listSearch]);

  function goList() {
    setView('list');
    setEditBracketId(null);
    setEditStages([]);
    setFillMasterUbId(null);
    setFillBracketName('');
  }

  function openCreate() {
    setPageMsg(null);
    setBIdentifier('');
    setBName('');
    setBDesc('');
    setBImage(null);
    setPageMsg(null);
    const first = bracketTemplates[0];
    if (first) {
      setBTemplateId(first.id);
      applyBracketTemplate(first, setStructureKind, setBN);
    } else {
      setBTemplateId('custom');
    }
    setView('create');
  }

  function onTemplateChange(next: BracketTemplateChoice) {
    setBTemplateId(next);
    if (next === 'custom') return;
    const tpl = bracketTemplates.find((t) => t.id === next);
    if (tpl) applyBracketTemplate(tpl, setStructureKind, setBN);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setPageMsg(null);
    const identifier = bIdentifier.trim();
    if (!identifier) {
      setPageMsg({ type: 'err', text: 'Identifier is required.' });
      return;
    }
    if (/\s/.test(identifier)) {
      setPageMsg({
        type: 'err',
        text: 'Identifier cannot contain spaces.',
      });
      return;
    }

    const name = bName.trim();
    if (!name) {
      setPageMsg({ type: 'err', text: 'Display name is required.' });
      return;
    }
    if (!Number.isFinite(bN) || bN < 2) {
      setPageMsg({ type: 'err', text: 'Number of contestants must be at least 2.' });
      return;
    }
    if (structureKind === 'GROUP_KNOCKOUT' && bN % 4 !== 0) {
      setPageMsg({
        type: 'err',
        text: 'For group & knockout, use a multiple of 4 contestants.',
      });
      return;
    }

    const bracket_contestants: { contestant_id: number; seed: number | null }[] =
      [];
    const seen = new Set<number>();
    for (const row of assignRows) {
      const cid = row.contestant_id.trim();
      if (!cid) continue;
      const contestant_id = parseInt(cid, 10);
      if (!Number.isFinite(contestant_id)) {
        setPageMsg({ type: 'err', text: 'Invalid contestant selection.' });
        return;
      }
      if (seen.has(contestant_id)) {
        setPageMsg({ type: 'err', text: 'Each contestant can only appear once.' });
        return;
      }
      seen.add(contestant_id);
      const seedRaw = row.seed.trim();
      const seed = seedRaw === '' ? null : parseInt(seedRaw, 10);
      if (seedRaw !== '' && !Number.isFinite(seed)) {
        setPageMsg({ type: 'err', text: 'Seeds must be numbers.' });
        return;
      }
      bracket_contestants.push({ contestant_id, seed });
    }

    let metadata: unknown = null;
    try {
      metadata = parseMetadataJson(bMetadata);
    } catch {
      setPageMsg({ type: 'err', text: 'Metadata must be valid JSON.' });
      return;
    }

    setCreateBusy(true);
    try {
      const structure_config = buildStructureConfig({
        structureKind,
        bNumGroups,
        bMatchesPer,
        bQualify,
        bPtWin,
        bPtTie,
        bPtLoss,
        bTiesAllowed,
        bGroupExactPts,
        bGroupAdvancerPts,
        bGroupRandom,
        bChampionPts,
        bThirdPlacePts: bThird ? bThirdPlacePts : 0,
        bKoLegs,
        bKoET,
        bKoPK,
        bKoPickPts,
        bKoRandom,
      });

      const fd = new FormData();
      if (bTemplateId !== 'custom' && typeof bTemplateId === 'number') {
        fd.append('template_id', String(bTemplateId));
      } else {
        fd.append('structure', structureKind);
      }
      fd.append('identifier', identifier);
      fd.append('name', name);
      if (bDesc.trim()) fd.append('description', bDesc.trim());
      fd.append('number_of_contestants', String(bN));
      if (bThird) fd.append('has_third_place', 'true');
      fd.append('randomize_seeds_per_challenge', bRand ? 'true' : 'false');
      fd.append('show_seeds', bShowSeeds ? 'true' : 'false');
      if (metadata != null) {
        fd.append('metadata', JSON.stringify(metadata));
      }
      fd.append('structure_config', JSON.stringify(structure_config));
      if (bracket_contestants.length > 0) {
        fd.append('bracket_contestants', JSON.stringify(bracket_contestants));
      }
      if (bImage) fd.append('image', bImage);
      const { bracket } = await adminCreateBracket(fd);
      setBrackets((prev) => [bracket, ...prev]);
      goList();
      setPageMsg({
        type: 'ok',
        text: `Created bracket “${bracket.name}”.`,
      });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not create bracket.',
      });
    } finally {
      setCreateBusy(false);
    }
  }

  async function startBracketEdit(b: BracketSummary) {
    setPageMsg(null);
    setView('edit');
    setEditBracketId(b.id);
    setEditIdentifier(b.identifier);
    setEditName(b.name);
    setEditDesc(b.description ?? '');
    setEditImage(null);
    setEditExistingImageUrl(b.image_url ?? null);
    setEditShowSeeds(b.show_seeds !== false);
    setEditRand(b.randomize_seeds_per_challenge);
    setEditThird(b.has_third_place_match ?? false);
    setEditChampionPts(b.points_champion ?? 0);
    setEditThirdPlacePts(b.points_third_place_winner ?? 0);
    setEditMetadata(metadataToText(b.metadata));
    setEditStages([]);
    setEditLoadBusy(true);
    try {
      const { bracket } = await getBracket(b.id);
      setEditShowSeeds(bracket.show_seeds !== false);
      setEditRand(bracket.randomize_seeds_per_challenge);
      setEditThird(bracket.has_third_place_match ?? false);
      setEditChampionPts(bracket.points_champion ?? 0);
      setEditThirdPlacePts(bracket.points_third_place_winner ?? 0);
      setEditMetadata(metadataToText(bracket.metadata));
      setEditStages(
        [...bracket.stages].sort((a, c) => a.order - c.order),
      );
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not load bracket.',
      });
    } finally {
      setEditLoadBusy(false);
    }
  }

  async function saveBracketEdit(e: React.FormEvent) {
    e.preventDefault();
    if (editBracketId == null) return;
    let metadata: unknown = null;
    try {
      metadata = parseMetadataJson(editMetadata);
    } catch {
      setPageMsg({ type: 'err', text: 'Metadata must be valid JSON.' });
      return;
    }

    setEditBusy(true);
    try {
      const fd = new FormData();
      fd.append('name', editName.trim());
      fd.append('description', editDesc.trim());
      fd.append('show_seeds', editShowSeeds ? 'true' : 'false');
      fd.append('randomize_seeds_per_challenge', editRand ? 'true' : 'false');
      fd.append('has_third_place_match', editThird ? 'true' : 'false');
      fd.append('points_champion', String(editChampionPts));
      fd.append('points_third_place_winner', String(editThird ? editThirdPlacePts : 0));
      fd.append('metadata', JSON.stringify(metadata));
      if (editImage) fd.append('image', editImage);
      await adminUpdateBracket(editBracketId, fd);
      const stageRes = await adminUpdateBracketStages(
        editBracketId,
        editStages.map(stageToAdminPatch),
      );
      const bracket = stageRes.bracket;
      setBrackets((prev) =>
        prev.map((r) =>
          r.id === bracket.id
            ? {
                ...r,
                name: bracket.name,
                description: bracket.description,
                image_url: bracket.image_url,
                show_seeds: bracket.show_seeds,
                randomize_seeds_per_challenge: bracket.randomize_seeds_per_challenge,
                has_third_place_match: bracket.has_third_place_match,
                points_champion: bracket.points_champion,
                points_third_place_winner: bracket.points_third_place_winner,
                metadata: bracket.metadata,
                challenge_count:
                  r.challenge_count ?? bracket.challenge_count ?? 0,
              }
            : r,
        ),
      );
      goList();
      setPageMsg({
        type: 'ok',
        text: `Saved “${bracket.name}”.`,
      });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not save bracket.',
      });
    } finally {
      setEditBusy(false);
    }
  }

  async function confirmDeleteBracket() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await adminDeleteBracket(deleteTarget.id);
      setBrackets((prev) => prev.filter((b) => b.id !== deleteTarget.id));
      if (editBracketId === deleteTarget.id) goList();
      setDeleteTarget(null);
      setPageMsg({ type: 'ok', text: 'Bracket deleted.' });
    } catch (err) {
      setPageMsg({
        type: 'err',
        text: err instanceof ApiError ? err.message : 'Could not delete bracket.',
      });
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function openMasterFill(b: BracketSummary) {
    try {
      const { bracket } = await getBracket(b.id);
      const masterId = bracket.master_user_bracket_id;
      if (masterId == null) {
        setLoadErr('No master bracket found for this tournament.');
        return;
      }
      setFillBracketName(b.name);
      setFillMasterUbId(masterId);
      setView('master');
    } catch (e) {
      setLoadErr(
        e instanceof ApiError ? e.message : 'Could not open master bracket.',
      );
    }
  }

  if (view === 'create') {
    return (
      <div className="admin-page">
        <AdminBackBar label="Brackets" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Create Bracket</h2>
          <p>
            Identifier is unique and has no spaces. Display name is what players
            see. Players join via challenges on the home page.
          </p>
        </header>
        <div className="card__body">
          <form onSubmit={onCreate}>
            {pageMsg ? (
              <div
                className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
              >
                {pageMsg.text}
              </div>
            ) : null}

            <div className="field">
              <label htmlFor="bracket-template">Structure template</label>
              <select
                id="bracket-template"
                className="select"
                value={
                  bTemplateId === '' ? '' : String(bTemplateId)
                }
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === 'custom') {
                    onTemplateChange('custom');
                    return;
                  }
                  const id = parseInt(raw, 10);
                  if (Number.isFinite(id)) onTemplateChange(id);
                }}
                required
                disabled={createBusy || bracketTemplates.length === 0}
              >
                {bracketTemplates.length === 0 ? (
                  <option value="custom">Custom structure</option>
                ) : (
                  bracketTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))
                )}
                <option value="custom">Custom structure…</option>
              </select>
              {selectedTemplate?.description ? (
                <p className="field__hint">{selectedTemplate.description}</p>
              ) : null}
              {bTemplateId === 'custom' ? (
                <div className="field" style={{ marginTop: '0.75rem' }}>
                  <label htmlFor="bracket-structure">Structure</label>
                  <select
                    id="bracket-structure"
                    className="select"
                    value={structureKind}
                    onChange={(e) =>
                      setStructureKind(e.target.value as BracketStructureType)
                    }
                    disabled={createBusy}
                  >
                    <option value="SINGLE_ELIM">Single elimination</option>
                    <option value="GROUP_KNOCKOUT">Group stage + knockout</option>
                  </select>
                </div>
              ) : selectedTemplate ? (
                <p className="field__hint">
                  {structureKindLabel(selectedTemplate.template_type)} — stages
                  are created automatically from the team count.
                </p>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="bracket-identifier">Identifier</label>
              <input
                id="bracket-identifier"
                className="input"
                value={bIdentifier}
                onChange={(e) =>
                  setBIdentifier(e.target.value.replace(/\s/g, ''))
                }
                maxLength={64}
                required
                disabled={createBusy}
                placeholder="e.g. fifa-world-cup-2026"
                autoComplete="off"
                spellCheck={false}
              />
            </div>

            <div className="form-grid form-grid--2">
              <div className="field">
                <label htmlFor="bracket-name">Display Name</label>
                <input
                  id="bracket-name"
                  className="input"
                  value={bName}
                  onChange={(e) => setBName(e.target.value)}
                  maxLength={100}
                  required
                  disabled={createBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="bracket-n">Number of Contestants</label>
                <input
                  id="bracket-n"
                  className="input"
                  type="number"
                  min={2}
                  max={128}
                  value={bN}
                  onChange={(e) => setBN(parseInt(e.target.value, 10) || 2)}
                  disabled={createBusy}
                />
              </div>
            </div>

            <div className="field">
              <label htmlFor="bracket-desc">Description</label>
              <textarea
                id="bracket-desc"
                className="textarea"
                rows={2}
                value={bDesc}
                onChange={(e) => setBDesc(e.target.value)}
                disabled={createBusy}
              />
            </div>

            <div className="field">
              <label htmlFor="bracket-image">Image</label>
              <input
                id="bracket-image"
                className="input"
                type="file"
                accept="image/*"
                disabled={createBusy}
                onChange={(e) => setBImage(e.target.files?.[0] ?? null)}
              />
              {bImagePreview ? (
                <div className="photo-preview">
                  <img src={bImagePreview} alt="" />
                  {bImage ? (
                    <span className="photo-preview__label">{bImage.name}</span>
                  ) : null}
                </div>
              ) : null}
            </div>

            {isSingleElim || structureKind === 'GROUP_KNOCKOUT' ? (
              <div className="form-grid form-grid--2 form-grid--align-end">
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={bThird}
                    onChange={(e) => setBThird(e.target.checked)}
                    disabled={createBusy}
                  />
                  Third-place match
                </label>
                <div className="field">
                  <label htmlFor="b-third-place-pts">Points for 3rd place winner</label>
                  <AdminNumberInput
                    id="b-third-place-pts"
                    value={bThirdPlacePts}
                    onChange={setBThirdPlacePts}
                    disabled={createBusy || !bThird}
                  />
                </div>
              </div>
            ) : null}
            <div className="field">
              <label htmlFor="b-champion-pts">Points for champion</label>
              <AdminNumberInput
                id="b-champion-pts"
                value={bChampionPts}
                onChange={setBChampionPts}
                disabled={createBusy}
              />
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={bRand}
                onChange={(e) => setBRand(e.target.checked)}
                disabled={createBusy}
              />
              Randomize seeds for each challenge
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={bShowSeeds}
                onChange={(e) => setBShowSeeds(e.target.checked)}
                disabled={createBusy}
              />
              Show seed numbers in the bracket
            </label>

            <div className="field">
              <label htmlFor="bracket-metadata">Bracket metadata (JSON)</label>
              <textarea
                id="bracket-metadata"
                className="textarea textarea--mono"
                rows={4}
                value={bMetadata}
                onChange={(e) => setBMetadata(e.target.value)}
                disabled={createBusy}
                placeholder={'{\n  "tournament_type": "world_cup_2026"\n}'}
                spellCheck={false}
              />
            </div>

            <details className="admin-details">
              <summary>Structure &amp; scoring defaults</summary>
              <div className="admin-details__body">
                {!isSingleElim ? (
                  <>
                    <p className="admin-details__subtitle">Group stage</p>
                    <div className="form-grid form-grid--2">
                      <div className="field">
                        <label htmlFor="b-num-groups">Number of groups</label>
                        <input
                          id="b-num-groups"
                          className="input"
                          type="number"
                          min={1}
                          placeholder={`Auto (${Math.floor(bN / 4) || '—'})`}
                          value={bNumGroups}
                          onChange={(e) => setBNumGroups(e.target.value)}
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-qualify">Qualifiers per group</label>
                        <input
                          id="b-qualify"
                          className="input"
                          type="number"
                          min={1}
                          value={bQualify}
                          onChange={(e) =>
                            setBQualify(parseInt(e.target.value, 10) || 1)
                          }
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-matches">Matches per team</label>
                        <input
                          id="b-matches"
                          className="input"
                          type="number"
                          min={1}
                          value={bMatchesPer}
                          onChange={(e) =>
                            setBMatchesPer(parseInt(e.target.value, 10) || 1)
                          }
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-group-exact-pts">Points per exact position</label>
                        <AdminNumberInput
                          id="b-group-exact-pts"
                          value={bGroupExactPts}
                          onChange={setBGroupExactPts}
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-group-advancer-pts">Points per advancer</label>
                        <AdminNumberInput
                          id="b-group-advancer-pts"
                          value={bGroupAdvancerPts}
                          onChange={setBGroupAdvancerPts}
                          disabled={createBusy}
                        />
                      </div>
                    </div>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={bTiesAllowed}
                        onChange={(e) => setBTiesAllowed(e.target.checked)}
                        disabled={createBusy}
                      />
                      Ties allowed in groups
                    </label>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={bGroupRandom}
                        onChange={(e) => setBGroupRandom(e.target.checked)}
                        disabled={createBusy}
                      />
                      Random draw for group stage
                    </label>
                    <div className="form-grid form-grid--3">
                      <div className="field">
                        <label htmlFor="b-pt-win">Points per win</label>
                        <input
                          id="b-pt-win"
                          className="input"
                          type="number"
                          min={0}
                          value={bPtWin}
                          onChange={(e) =>
                            setBPtWin(parseInt(e.target.value, 10) || 0)
                          }
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-pt-tie">Points per tie</label>
                        <input
                          id="b-pt-tie"
                          className="input"
                          type="number"
                          min={0}
                          value={bPtTie}
                          onChange={(e) =>
                            setBPtTie(parseInt(e.target.value, 10) || 0)
                          }
                          disabled={createBusy}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="b-pt-loss">Points per loss</label>
                        <input
                          id="b-pt-loss"
                          className="input"
                          type="number"
                          min={0}
                          value={bPtLoss}
                          onChange={(e) =>
                            setBPtLoss(parseInt(e.target.value, 10) || 0)
                          }
                          disabled={createBusy}
                        />
                      </div>
                    </div>
                  </>
                ) : null}
                <p className="admin-details__subtitle">Knockout rounds</p>
                <div className="form-grid form-grid--2">
                  <div className="field">
                    <label htmlFor="b-ko-legs">Legs per matchup</label>
                    <input
                      id="b-ko-legs"
                      className="input"
                      type="number"
                      min={1}
                      value={bKoLegs}
                      onChange={(e) =>
                        setBKoLegs(parseInt(e.target.value, 10) || 1)
                      }
                      disabled={createBusy}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="b-ko-pick-pts">Points per correct pick</label>
                    <input
                      id="b-ko-pick-pts"
                      className="input"
                      type="number"
                      min={1}
                      value={bKoPickPts}
                      onChange={(e) =>
                        setBKoPickPts(parseInt(e.target.value, 10) || 1)
                      }
                      disabled={createBusy}
                    />
                  </div>
                </div>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={bKoET}
                    onChange={(e) => setBKoET(e.target.checked)}
                    disabled={createBusy}
                  />
                  Extra time in knockout
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={bKoPK}
                    onChange={(e) => setBKoPK(e.target.checked)}
                    disabled={createBusy}
                  />
                  Penalty shootout in knockout
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={bKoRandom}
                    onChange={(e) => setBKoRandom(e.target.checked)}
                    disabled={createBusy}
                  />
                  Random draw for knockout
                </label>
              </div>
            </details>

            <div className="assign-section">
              <div className="assign-section__head">
                <h3 className="assign-section__title">Contestants</h3>
                <input
                  type="search"
                  className="input assign-section__search"
                  placeholder="Filter catalog…"
                  value={assignSearch}
                  onChange={(e) => setAssignSearch(e.target.value)}
                  aria-label="Filter contestants"
                  disabled={createBusy}
                />
              </div>
              {contestants.length === 0 ? (
                <p className="field__hint">
                  Add contestants in the Contestants tab first.
                </p>
              ) : (
                <div className="assign-list assign-list--compact">
                  {assignRows.map((row, i) => (
                    <div key={i} className="assign-list__row">
                      <input
                        className="input"
                        type="number"
                        min={1}
                        aria-label={`Seed ${i + 1}`}
                        placeholder="Seed"
                        value={row.seed}
                        onChange={(e) => {
                          const v = e.target.value;
                          setAssignRows((rows) =>
                            rows.map((r, j) => (j === i ? { ...r, seed: v } : r)),
                          );
                        }}
                        disabled={createBusy}
                      />
                      <select
                        className="select"
                        aria-label={`Contestant ${i + 1}`}
                        value={row.contestant_id}
                        onChange={(e) => {
                          const v = e.target.value;
                          setAssignRows((rows) =>
                            rows.map((r, j) =>
                              j === i ? { ...r, contestant_id: v } : r,
                            ),
                          );
                        }}
                        disabled={createBusy}
                      >
                        <option value="">Select…</option>
                        {contestantOptions.map((c) => (
                          <option key={c.id} value={String(c.id)}>
                            {c.name} ({c.identifier})
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              type="submit"
              className="btn btn--primary"
              disabled={createBusy}
              style={{ marginTop: '1rem' }}
            >
              {createBusy ? 'Creating…' : 'Create Bracket'}
            </button>
          </form>
        </div>
      </section>
      </div>
    );
  }

  if (view === 'master' && fillMasterUbId != null) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Brackets" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Master bracket — {fillBracketName}</h2>
          </header>
          <div className="card__body">
            <BracketFill
              userBracketId={fillMasterUbId}
              allowMasterEdit
              showGroupResultsModeControl
            />
          </div>
        </section>
      </div>
    );
  }

  if (view === 'edit' && editBracketId != null) {
    return (
      <div className="admin-page">
        <AdminBackBar label="Brackets" onBack={goList} />
        <section className="card">
          <header className="card__header">
            <h2>Edit Bracket</h2>
          </header>
          <div className="card__body">
            {editLoadBusy ? (
              <p className="field__hint">Loading bracket settings…</p>
            ) : null}
            <form onSubmit={saveBracketEdit}>
              {pageMsg ? (
                <div
                  className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
                >
                  {pageMsg.text}
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="edit-bracket-identifier">Identifier</label>
                <input
                  id="edit-bracket-identifier"
                  className="input"
                  value={editIdentifier}
                  readOnly
                  disabled
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-name">Display Name</label>
                <input
                  id="edit-bracket-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-desc">Description</label>
                <textarea
                  id="edit-bracket-desc"
                  className="textarea"
                  rows={2}
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  disabled={editBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-image">Image</label>
                <input
                  id="edit-bracket-image"
                  className="input"
                  type="file"
                  accept="image/*"
                  disabled={editBusy}
                  onChange={(e) => setEditImage(e.target.files?.[0] ?? null)}
                />
                {editImagePreview ? (
                  <div className="photo-preview">
                    <img src={editImagePreview} alt="" />
                    {editImage ? (
                      <span className="photo-preview__label">{editImage.name}</span>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={editShowSeeds}
                  onChange={(e) => setEditShowSeeds(e.target.checked)}
                  disabled={editBusy || editLoadBusy}
                />
                Show seed numbers in the bracket
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={editRand}
                  onChange={(e) => setEditRand(e.target.checked)}
                  disabled={editBusy || editLoadBusy}
                />
                Randomize seeds for each challenge
              </label>
              <div className="form-grid form-grid--2 form-grid--align-end">
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={editThird}
                    onChange={(e) => setEditThird(e.target.checked)}
                    disabled={editBusy || editLoadBusy}
                  />
                  Third-place match
                </label>
                <div className="field">
                  <label htmlFor="edit-third-place-pts">Points for 3rd place winner</label>
                  <AdminNumberInput
                    id="edit-third-place-pts"
                    value={editThirdPlacePts}
                    onChange={setEditThirdPlacePts}
                    disabled={editBusy || editLoadBusy || !editThird}
                  />
                </div>
              </div>
              <div className="field">
                <label htmlFor="edit-champion-pts">Points for champion</label>
                <AdminNumberInput
                  id="edit-champion-pts"
                  value={editChampionPts}
                  onChange={setEditChampionPts}
                  disabled={editBusy || editLoadBusy}
                />
              </div>
              <div className="field">
                <label htmlFor="edit-bracket-metadata">Bracket metadata (JSON)</label>
                <textarea
                  id="edit-bracket-metadata"
                  className="textarea textarea--mono"
                  rows={5}
                  value={editMetadata}
                  onChange={(e) => setEditMetadata(e.target.value)}
                  disabled={editBusy || editLoadBusy}
                  spellCheck={false}
                />
              </div>
              {editStages.length > 0 ? (
                <div className="stage-editor-list">
                  <h3 className="assign-section__title">Stages</h3>
                  {editStages.map((stage) => (
                    <BracketStageEditor
                      key={stage.id}
                      stage={stage}
                      isFirstKnockout={stage.id === firstKnockoutStageId}
                      hasGroupStage={editHasGroupStage}
                      disabled={editBusy || editLoadBusy}
                      onChange={(next) =>
                        setEditStages((rows) =>
                          rows.map((r) => (r.id === next.id ? next : r)),
                        )
                      }
                    />
                  ))}
                </div>
              ) : null}
              <button
                type="submit"
                className="btn btn--primary"
                disabled={editBusy || editLoadBusy}
                style={{ marginTop: '1rem' }}
              >
                {editBusy ? 'Saving…' : 'Save Changes'}
              </button>
            </form>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="admin-page">
      {loadErr ? <div className="alert alert--error">{loadErr}</div> : null}

      <section className="card catalog-card">
        <AdminCatalogToolbar
          title="Brackets"
          countLabel={
            filteredBrackets.length === brackets.length
              ? `${brackets.length} in catalog`
              : `${filteredBrackets.length} of ${brackets.length} in catalog`
          }
          search={listSearch}
          onSearchChange={setListSearch}
          searchLabel="Search brackets"
          createLabel="Create Bracket"
          onCreate={openCreate}
        />
        <div className="card__body catalog-card__body">
          {pageMsg ? (
            <div
              className={`alert alert--${pageMsg.type === 'ok' ? 'success' : 'error'}`}
              role="status"
            >
              {pageMsg.text}
            </div>
          ) : null}
          {filteredBrackets.length === 0 && !loadErr ? (
            <p className="empty-state empty-state--compact">
              <strong>
                {brackets.length === 0 ? 'No brackets yet' : 'No matches'}
              </strong>
              {brackets.length === 0
                ? 'Create a bracket to run challenges.'
                : 'Try a different search.'}
            </p>
          ) : (
            <ul className="catalog-list">
              {filteredBrackets.map((b) => {
                return (
                <li key={b.id} className="catalog-list__row catalog-shelf__row">
                  <div className="catalog-shelf__main">
                    {b.image_url ? (
                      <img
                        className="catalog-list__avatar"
                        src={b.image_url}
                        alt=""
                      />
                    ) : (
                      <span className="catalog-list__avatar catalog-list__avatar--ph">
                        {b.name.charAt(0)}
                      </span>
                    )}
                    <span className="catalog-list__main">
                      <span className="catalog-list__name">{b.name}</span>
                      <span className="catalog-list__id">{b.identifier}</span>
                    </span>
                  </div>
                  <div className="catalog-shelf__actions">
                    <button
                      type="button"
                      className="btn-icon"
                      title="Edit"
                      aria-label={`Edit ${b.name}`}
                      onClick={() => void startBracketEdit(b)}
                    >
                      <IconPencil />
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--bracket"
                      title="Fill Master"
                      aria-label={`Fill master bracket for ${b.name}`}
                      onClick={() => void openMasterFill(b)}
                    >
                      {'}'} {'{'}
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-icon--danger"
                      title="Delete"
                      aria-label={`Delete ${b.name}`}
                      onClick={() =>
                        startDeleteTarget('bracket', b.id, b.name, setDeleteTarget)
                      }
                    >
                      <IconTrash />
                    </button>
                  </div>
                </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>


      <DeleteConfirmDialog
        open={deleteTarget != null}
        title="Delete Bracket?"
        label={deleteTarget?.label ?? ''}
        relatedRecords={deleteTarget?.relatedRecords}
        loadingRelated={deleteTarget?.loadingRelated}
        busy={deleteBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDeleteBracket()}
      />
    </div>
  );
}
