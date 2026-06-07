import type { ContestantTagInfo } from '../../utils/api';

import './admin-shared.css';

type Props = {
  showIdentifier?: boolean;
  identifierReadOnly?: boolean;
  identifier?: string;
  onIdentifierChange?: (value: string) => void;
  name: string;
  onNameChange: (value: string) => void;
  description: string;
  onDescriptionChange: (value: string) => void;
  imageUrl: string;
  onImageUrlChange: (value: string) => void;
  metadata: string;
  onMetadataChange: (value: string) => void;
  selectedTagIds: number[];
  onToggleTag: (tagId: number) => void;
  newTagNames: string;
  onNewTagNamesChange: (value: string) => void;
  allTags: ContestantTagInfo[];
  photoInputKey: number;
  onPhotoChange: (file: File | null) => void;
  photoPreview: string | null;
  photoName?: string;
  existingPhotoUrl?: string | null;
  disabled?: boolean;
};

export function ContestantFormFields({
  showIdentifier = false,
  identifierReadOnly = false,
  identifier,
  onIdentifierChange,
  name,
  onNameChange,
  description,
  onDescriptionChange,
  imageUrl,
  onImageUrlChange,
  metadata,
  onMetadataChange,
  selectedTagIds,
  onToggleTag,
  newTagNames,
  onNewTagNamesChange,
  allTags,
  photoInputKey,
  onPhotoChange,
  photoPreview,
  photoName,
  existingPhotoUrl,
  disabled,
}: Props) {
  return (
    <>
      {showIdentifier ? (
        <div className="field">
          <label htmlFor="contestant-identifier">Identifier</label>
          <input
            id="contestant-identifier"
            className="input"
            value={identifier}
            onChange={(e) =>
              onIdentifierChange?.(e.target.value.replace(/\s/g, ''))
            }
            maxLength={64}
            required
            readOnly={identifierReadOnly}
            disabled={disabled || identifierReadOnly}
            placeholder="e.g. brazil-2026"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      ) : null}

      <div className="field">
        <label htmlFor="contestant-name">Display Name</label>
        <input
          id="contestant-name"
          className="input"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          maxLength={100}
          required
          disabled={disabled}
        />
      </div>

      <div className="field">
        <label htmlFor="contestant-desc">Description</label>
        <textarea
          id="contestant-desc"
          className="textarea"
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={3}
          disabled={disabled}
          placeholder="Optional"
        />
      </div>

      <div className="field">
        <label htmlFor="contestant-image-url">Image URL</label>
        <input
          id="contestant-image-url"
          className="input"
          type="url"
          value={imageUrl}
          onChange={(e) => onImageUrlChange(e.target.value)}
          disabled={disabled}
          placeholder="https://…"
        />
        <p className="field__hint">
          External image link. Upload a photo below to override.
        </p>
      </div>

      <div className="field">
        <label htmlFor="contestant-photo">Photo Upload</label>
        {existingPhotoUrl && !photoName ? (
          <div className="photo-preview">
            <img src={existingPhotoUrl} alt="" />
            <span className="photo-preview__label">Current photo</span>
          </div>
        ) : null}
        <input
          key={photoInputKey}
          id="contestant-photo"
          className="input"
          type="file"
          accept="image/*"
          disabled={disabled}
          onChange={(e) => onPhotoChange(e.target.files?.[0] ?? null)}
        />
        {photoPreview && photoName ? (
          <div className="photo-preview">
            <img src={photoPreview} alt="" />
            <span className="photo-preview__label">{photoName}</span>
          </div>
        ) : null}
      </div>

      <div className="field">
        <label>Tags</label>
        {allTags.length === 0 ? (
          <p className="field__hint">No tags yet. Add new tags below.</p>
        ) : (
          <div className="tag-picker">
            {allTags.map((tag) => (
              <label key={tag.id} className="tag-picker__item">
                <input
                  type="checkbox"
                  checked={selectedTagIds.includes(tag.id)}
                  onChange={() => onToggleTag(tag.id)}
                  disabled={disabled}
                />
                {tag.name}
              </label>
            ))}
          </div>
        )}
        <label htmlFor="contestant-new-tags" className="field__hint">
          New tags (comma-separated)
        </label>
        <input
          id="contestant-new-tags"
          className="input"
          value={newTagNames}
          onChange={(e) => onNewTagNamesChange(e.target.value)}
          disabled={disabled}
          placeholder="e.g. soccer, national team"
        />
      </div>

      <div className="field">
        <label htmlFor="contestant-metadata">Metadata (JSON)</label>
        <textarea
          id="contestant-metadata"
          className="textarea textarea--mono"
          rows={4}
          value={metadata}
          onChange={(e) => onMetadataChange(e.target.value)}
          disabled={disabled}
          placeholder="{}"
          spellCheck={false}
        />
      </div>
    </>
  );
}
