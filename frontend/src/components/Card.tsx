import { useId, type ReactNode } from 'react';

interface CardProps {
  title?: string;
  eyebrow?: string;
  /** Right-aligned header content (a key, a window label, a control). */
  action?: ReactNode;
  className?: string;
  children: ReactNode;
  as?: 'section' | 'article' | 'div';
}

/** A tonal panel: a surface layer with no hard border, an optional header. */
export function Card({ title, eyebrow, action, className = '', children, as: Tag = 'section' }: CardProps) {
  const headingId = useId();
  return (
    <Tag className={`panel ${className}`.trim()} aria-labelledby={title ? headingId : undefined}>
      {(title || eyebrow || action) && (
        <header className="panel__header">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && (
              <h3 id={headingId} className="panel__title">
                {title}
              </h3>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </Tag>
  );
}
