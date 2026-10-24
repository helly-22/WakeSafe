import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <div className="state">
      <h1 className="page-header__title">Page not found</h1>
      <Link className="btn" to="/">
        Back to Overview
      </Link>
    </div>
  );
}
