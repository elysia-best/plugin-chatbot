import { Wrench } from 'lucide-react';
import { CheckRow } from '../ui/Field.jsx';
import './ToolSelection.css';

/**
 * 工具默认值选择器：null 表示继承当前模式下全部可用工具，
 * 取消继承后可逐个勾选。
 */
export default function ToolSelection({ value, tools, onChange }) {
  const inherited = value == null;
  const selected = value || [];

  function toggle(name) {
    onChange(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name]);
  }

  return (
    <section className="tool-selection">
      <header className="tool-selection__head">
        <strong>
          <Wrench size={15} />
          工具默认
        </strong>
        <CheckRow
          label="继承可用工具"
          checked={inherited}
          onChange={(checked) => onChange(checked ? null : tools.map((tool) => tool.name))}
        />
      </header>

      {inherited ? (
        <p className="tool-selection__hint">
          继承后会自动跟随当前模式暴露的全部工具；取消继承可逐个限制。
        </p>
      ) : (
        <div className="tool-selection__grid">
          {tools.map((tool) => (
            <CheckRow
              key={tool.name}
              label={tool.name}
              title={tool.description}
              checked={selected.includes(tool.name)}
              onChange={() => toggle(tool.name)}
            />
          ))}
          {!tools.length ? <p className="tool-selection__hint">当前模式没有可用工具。</p> : null}
        </div>
      )}
    </section>
  );
}
