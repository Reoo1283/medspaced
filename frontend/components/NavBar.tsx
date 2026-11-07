"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";

const publicLinks = [
  { href: "/", label: "Panel" },
  { href: "/study", label: "Çalış" },
  { href: "/exam", label: "Sınav" },
  { href: "/skills", label: "Yetenekler" },
];

export default function NavBar() {
  const { user, loading, logout, canReview } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const links = [...publicLinks];
  if (canReview) {
    links.push({ href: "/content", label: "İçerik" });
    links.push({ href: "/review", label: "İnceleme" });
    links.push({ href: "/admin/skills", label: "Yetenek Yönetimi" });
  }

  return (
    <header className="nav">
      <div className="nav-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">M</span>
          <span>
            MedSpaced
            <small>anestezi tekrar platformu</small>
          </span>
        </Link>
        <nav className="nav-links">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={pathname === link.href ? "active" : ""}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="nav-user">
          {loading ? null : user ? (
            <>
              <span className="nav-name">
                {user.full_name || user.email}
                <small>{user.role}</small>
              </span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  logout();
                  router.push("/login");
                }}
              >
                Çıkış
              </button>
            </>
          ) : (
            <>
              <Link className="btn btn-ghost btn-sm" href="/login">
                Giriş
              </Link>
              <Link className="btn btn-primary btn-sm" href="/register">
                Kayıt ol
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
