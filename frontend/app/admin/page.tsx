"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import Protected from "@/components/Protected";
import { Empty, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Role, User } from "@/lib/types";

function AdminScreen() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("reviewer");

  const load = useCallback(async () => {
    setError(null);
    try {
      setUsers(await api<User[]>("/auth/users"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kullanıcılar yüklenemedi");
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api<User>("/auth/users", {
        method: "POST",
        body: JSON.stringify({ email, full_name: fullName, password, role }),
      });
      setMessage(`${email} kullanıcısı ${role} rolüyle oluşturuldu.`);
      setEmail("");
      setFullName("");
      setPassword("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kullanıcı oluşturulamadı");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Yönetim"
        description="Kullanıcıları görüntüleyin ve yeni eğitmen/yönetici hesapları oluşturun."
        actions={
          <Link className="btn btn-ghost" href="/admin/skills">
            Yetenek ağacı yönetimi
          </Link>
        }
      />
      {error ? <div className="error-box">{error}</div> : null}
      {message ? <div className="success-box">{message}</div> : null}

      <div className="grid grid-2">
        <form className="card" onSubmit={createUser}>
          <h2>Yeni kullanıcı</h2>
          <div className="field">
            <label htmlFor="fullName">Ad soyad</label>
            <input
              id="fullName"
              className="input"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="email">E-posta</label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Geçici parola</label>
            <input
              id="password"
              className="input"
              type="password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="role">Rol</label>
            <select
              id="role"
              className="select"
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
            >
              <option value="student">student</option>
              <option value="reviewer">reviewer</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Oluşturuluyor…" : "Kullanıcı oluştur"}
          </button>
        </form>

        <div className="card">
          <div className="section-title">
            <h2>Kullanıcılar</h2>
            <span className="muted small">{users?.length ?? 0} kişi</span>
          </div>
          {users === null ? (
            <p className="muted">Yükleniyor…</p>
          ) : users.length === 0 ? (
            <Empty>Kullanıcı bulunamadı.</Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ad</th>
                    <th>E-posta</th>
                    <th>Rol</th>
                    <th>Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.full_name}</td>
                      <td className="muted small">{user.email}</td>
                      <td>
                        <span className={`badge badge-${user.role}`}>{user.role}</span>
                      </td>
                      <td>
                        <span className={`badge ${user.is_active ? "badge-approved" : "badge-rejected"}`}>
                          {user.is_active ? "aktif" : "pasif"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function AdminPage() {
  return (
    <Protected roles={["admin"]}>
      <AdminScreen />
    </Protected>
  );
}
