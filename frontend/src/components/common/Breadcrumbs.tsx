import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { getBreadcrumbTrail } from "@/utils/navigation";

export function Breadcrumbs() {
  const location = useLocation();
  const trail = getBreadcrumbTrail(location.pathname);

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm">
      {trail.map((crumb, index) => {
        const isLast = index === trail.length - 1;
        return (
          <Fragment key={crumb.href}>
            {index > 0 ? <ChevronRight className="h-3.5 w-3.5 text-content-muted" aria-hidden="true" /> : null}
            {isLast ? (
              <span className="font-semibold text-content-primary" aria-current="page">
                {crumb.label}
              </span>
            ) : (
              <Link to={crumb.href} className="text-content-muted transition hover:text-content-primary">
                {crumb.label}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
