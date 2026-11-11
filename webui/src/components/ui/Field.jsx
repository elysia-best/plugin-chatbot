import { ChevronDown, Search } from 'lucide-react';
import './Field.css';

/** 表单字段：雾灰底、16px 圆角、聚焦转白底 + 4px 靛蓝外环。 */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
  wide = false,
  hint,
  min,
  max,
  step,
  disabled = false,
  rows,
  code = false,
  name,
  autoComplete,
  onKeyDown,
}) {
  const id = name ? `field-${name}` : undefined;
  const common = {
    id,
    value: value ?? '',
    placeholder,
    disabled,
    onKeyDown,
    onChange: (event) => onChange(event.target.value),
  };

  return (
    <label className={`ui-field${wide ? ' ui-field--wide' : ''}`}>
      <span className="ui-field__label">{label}</span>
      {type === 'textarea' ? (
        <textarea
          {...common}
          rows={rows}
          className={`ui-input ui-textarea${code ? ' ui-textarea--code' : ''}`}
        />
      ) : (
        <input
          {...common}
          type={type}
          min={min}
          max={max}
          step={step}
          autoComplete={autoComplete}
          className="ui-input"
        />
      )}
      {hint ? <span className="ui-field__hint">{hint}</span> : null}
    </label>
  );
}

/** 下拉选择：隐藏原生箭头，用柔和的图标层替代。 */
export function SelectField({
  label,
  value,
  options,
  labels,
  onChange,
  wide = false,
  disabled = false,
  hint,
}) {
  return (
    <label className={`ui-field${wide ? ' ui-field--wide' : ''}`}>
      <span className="ui-field__label">{label}</span>
      <span className="ui-select">
        <select
          className="ui-input ui-select__control"
          value={value ?? ''}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {options.map((option, index) => (
            <option key={`${option}-${index}`} value={option}>
              {labels?.[index] || option || '默认'}
            </option>
          ))}
        </select>
        <ChevronDown className="ui-select__chevron" size={16} aria-hidden="true" />
      </span>
      {hint ? <span className="ui-field__hint">{hint}</span> : null}
    </label>
  );
}

/** 复选行：用于开关类配置。 */
export function CheckRow({ label, checked, onChange, disabled = false, title, description }) {
  return (
    <label className="ui-check" title={title}>
      <input
        type="checkbox"
        checked={Boolean(checked)}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="ui-check__box" aria-hidden="true">
        <svg viewBox="0 0 12 12" width="12" height="12">
          <path
            d="M2.5 6.2 4.8 8.5 9.5 3.8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="ui-check__text">
        {label}
        {description ? <small>{description}</small> : null}
      </span>
    </label>
  );
}

/** 搜索输入：带前置图标，用于列表筛选。 */
export function SearchInput({ value, onChange, placeholder = '搜索', label, wide = false }) {
  return (
    <label className={`ui-search${wide ? ' ui-field--wide' : ''}`}>
      <Search size={16} className="ui-search__icon" aria-hidden="true" />
      <input
        type="search"
        className="ui-input ui-search__control"
        value={value}
        placeholder={placeholder}
        aria-label={label || placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export default Field;
