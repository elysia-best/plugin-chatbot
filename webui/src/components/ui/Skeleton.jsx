import './Skeleton.css';

/** 骨架块：加载期间承接布局，避免内容跳动。 */
export default function Skeleton({ width = '100%', height = 14, radius = 8, className = '' }) {
  return (
    <span
      className={`ui-skeleton ${className}`.trim()}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

/** 表格骨架：按行数铺出占位行。 */
export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="ui-skeleton-rows" aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div className="ui-skeleton-rows__row" key={index}>
          <Skeleton width={38} height={38} radius={999} />
          <div className="ui-skeleton-rows__text">
            <Skeleton width="42%" height={13} />
            <Skeleton width="28%" height={10} />
          </div>
          <Skeleton width={96} height={26} radius={999} />
        </div>
      ))}
    </div>
  );
}
