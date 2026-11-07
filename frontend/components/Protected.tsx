"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

export default function Protected({
  children,
  roles,
}: {
  children: ReactNode;
  roles?: Role[];
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, router, pathname]);

  if (loading) {
    return <div className="card muted">Yükleniyor…</div>;
  }
  if (!user) {
    return <div className="card muted">Giriş sayfasına yönlendiriliyor…</div>;
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="card">
        <h2>Yetkisiz erişim</h2>
        <p className="muted">Bu sayfa yalnızca {roles.join(" / ")} rolleri içindir.</p>
      </div>
    );
  }
  return <>{children}</>;
}
