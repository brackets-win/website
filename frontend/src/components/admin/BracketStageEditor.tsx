import type { BracketStageInfo } from '../../utils/api';

import './admin-shared.css';

const KNOCKOUT_FILL_OPTIONS = [
  { value: 'standard', label: 'Standard' },
  { value: 'seeding', label: 'Seeding' },
  { value: 'mapping', label: 'Mapping' },
] as const;

type KnockoutFillMethod = (typeof KNOCKOUT_FILL_OPTIONS)[number]['value'];

function readKnockoutFillMethod(metadata: unknown): KnockoutFillMethod {
  if (
    metadata &&
    typeof metadata === 'object' &&
    'knockout_fill_method' in metadata
  ) {
    const raw = (metadata as { knockout_fill_method?: unknown })
      .knockout_fill_method;
    if (typeof raw === 'string') {
      const v = raw.trim().toLowerCase();
      if (KNOCKOUT_FILL_OPTIONS.some((o) => o.value === v)) {
        return v as KnockoutFillMethod;
      }
    }
  }
  return 'standard';
}

function setKnockoutFillMethod(
  metadata: unknown,
  method: KnockoutFillMethod,
): Record<string, unknown> {
  const base =
    metadata && typeof metadata === 'object' && !Array.isArray(metadata)
      ? { ...(metadata as Record<string, unknown>) }
      : {};
  base.knockout_fill_method = method;
  return base;
}

type Props = {
  stage: BracketStageInfo;
  onChange: (stage: BracketStageInfo) => void;
  disabled?: boolean;
  isFirstKnockout?: boolean;
};

function metadataText(value: unknown): string {
  if (value == null) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '';
  }
}

function parseMetadataInput(text: string): unknown {
  const t = text.trim();
  if (!t) return null;
  return JSON.parse(t) as unknown;
}

export function BracketStageEditor({
  stage,
  onChange,
  disabled,
  isFirstKnockout = false,
}: Props) {
  const isGroup = stage.stage_type === 'GROUP';
  const isKo = stage.stage_type === 'KNOCKOUT';

  return (
    <fieldset className="stage-editor">
      <legend>
        {stage.name}{' '}
        <span className="stage-editor__meta">
          #{stage.order} · {stage.stage_type.toLowerCase()}
        </span>
      </legend>

      <div className="form-grid form-grid--2">
        <div className="field">
          <label>Stage name</label>
          <input
            className="input"
            value={stage.name}
            onChange={(e) => onChange({ ...stage, name: e.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="field">
          <label>Points per correct pick</label>
          <input
            className="input"
            type="number"
            min={1}
            value={stage.points_per_correct_pick}
            onChange={(e) =>
              onChange({
                ...stage,
                points_per_correct_pick: parseInt(e.target.value, 10) || 1,
              })
            }
            disabled={disabled}
          />
        </div>
      </div>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={stage.is_random_draw}
          onChange={(e) =>
            onChange({ ...stage, is_random_draw: e.target.checked })
          }
          disabled={disabled}
        />
        Random draw for this stage
      </label>

      {isGroup && stage.group ? (
        <div className="stage-editor__block">
          <h4 className="stage-editor__subtitle">Group stage rules</h4>
          <div className="form-grid form-grid--2">
            <div className="field">
              <label>Number of groups</label>
              <input
                className="input"
                type="number"
                min={1}
                value={stage.group.number_of_groups}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      number_of_groups: parseInt(e.target.value, 10) || 1,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Qualifiers per group</label>
              <input
                className="input"
                type="number"
                min={1}
                value={stage.group.contestants_qualifying_per_group}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      contestants_qualifying_per_group:
                        parseInt(e.target.value, 10) || 1,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Matches per team</label>
              <input
                className="input"
                type="number"
                min={1}
                value={stage.group.matches_per_contestant}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      matches_per_contestant: parseInt(e.target.value, 10) || 1,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Remaining spots strategy</label>
              <select
                className="select"
                value={stage.group.remaining_spots_strategy ?? ''}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      remaining_spots_strategy: e.target.value || null,
                    },
                  })
                }
                disabled={disabled}
              >
                <option value="">None</option>
                <option value="HighestPlaceWithinGroup">Highest place in group</option>
                <option value="MostPointsAcrossGroups">Most points across groups</option>
              </select>
            </div>
            <div className="field">
              <label>Points per win</label>
              <input
                className="input"
                type="number"
                min={0}
                value={stage.group.points_per_win}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_win: parseInt(e.target.value, 10) || 0,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per tie</label>
              <input
                className="input"
                type="number"
                min={0}
                value={stage.group.points_per_tie}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_tie: parseInt(e.target.value, 10) || 0,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per loss</label>
              <input
                className="input"
                type="number"
                min={0}
                value={stage.group.points_per_loss}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_loss: parseInt(e.target.value, 10) || 0,
                    },
                  })
                }
                disabled={disabled}
              />
            </div>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.group.ties_allowed}
              onChange={(e) =>
                onChange({
                  ...stage,
                  group: { ...stage.group!, ties_allowed: e.target.checked },
                })
              }
              disabled={disabled}
            />
            Ties allowed
          </label>
        </div>
      ) : null}

      {isKo && stage.knockout ? (
        <div className="stage-editor__block">
          <h4 className="stage-editor__subtitle">Knockout rules</h4>
          <div className="field">
            <label>Number of legs</label>
            <input
              className="input"
              type="number"
              min={1}
              value={stage.knockout.number_of_legs}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    number_of_legs: parseInt(e.target.value, 10) || 1,
                  },
                })
              }
              disabled={disabled}
            />
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.has_extra_time}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    has_extra_time: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Extra time
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.has_penalty_shootout}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    has_penalty_shootout: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Penalty shootout
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.is_final}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    is_final: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Final (champion)
          </label>
          {isFirstKnockout ? (
            <div className="field" style={{ marginTop: '0.75rem' }}>
              <label htmlFor={`ko-fill-${stage.id}`}>
                Group → knockout fill
              </label>
              <select
                id={`ko-fill-${stage.id}`}
                className="select"
                value={readKnockoutFillMethod(stage.metadata)}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    metadata: setKnockoutFillMethod(
                      stage.metadata,
                      e.target.value as KnockoutFillMethod,
                    ),
                  })
                }
                disabled={disabled}
              >
                {KNOCKOUT_FILL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <p className="stage-editor__hint">
                Standard walks groups (A1 vs B2, …). Seeding uses ranked bracket
                slots. Mapping uses an explicit slot map in metadata.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="field">
        <label>Stage metadata (JSON)</label>
        <textarea
          className="textarea textarea--mono"
          rows={3}
          defaultValue={metadataText(stage.metadata)}
          key={`meta-${stage.id}-${metadataText(stage.metadata).length}`}
          onBlur={(e) => {
            try {
              const metadata = parseMetadataInput(e.target.value);
              onChange({ ...stage, metadata });
            } catch {
              /* keep previous until valid */
            }
          }}
          disabled={disabled}
          placeholder='{"group_knockout_mapping": …}'
          spellCheck={false}
        />
      </div>
    </fieldset>
  );
}
