export function Skeleton({ className = '', ...rest }) {
  return <div className={`skeleton rounded ${className}`} {...rest} />
}

export function SkeletonLine({ width = '100%', className = '' }) {
  return <Skeleton className={`h-3 ${className}`} style={{ width }} />
}
