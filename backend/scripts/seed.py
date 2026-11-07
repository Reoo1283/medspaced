"""Seed development data and an optional demo learning flow.

Usage:
    python -m scripts.seed
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.db import SessionLocal, init_db
from app.core.security import hash_password
from app.models import (
    ContentFile,
    Exercise,
    SkillNode,
    SkillPrerequisite,
    User,
    utcnow,
)
from app.services.content import process_file
from app.services.generation import generate_for_file

DEMO_FILENAME = "demo-anestezi-temelleri.md"

DEMO_CONTENT = """# Solunum Fizyolojisi ve Havayolu

Solunum sistemi oksijen alımı ve karbondioksit atılımından sorumludur. Alveoller gaz değişiminin gerçekleştiği temel yapılardır. Surfaktan alveollerin yüzey gerilimini azaltarak kollapsı önler. Preoksijenasyon, genel anestezi indüksiyonu öncesinde oksijen rezervini artırır. Zor havayolu riski taşıyan hastalarda alternatif havayolu planı önceden hazırlanmalıdır.

# İntravenöz Anestezikler

Propofol hızlı etkili intravenöz anestezik ajanlardan biridir. İndüksiyon sırasında hipotansiyon görülebilir. Ketamin dissosiyatif anestezi oluşturur ve analjezik etkisi vardır. Etomidat kardiyovasküler olarak daha stabildir ancak adrenal supresyon yapabilir. İndüksiyon dozları hastanın yaşı, kilosu ve komorbiditelerine göre ayarlanmalıdır.

# İnhalasyon Anestezikleri

Sevofluran indüksiyon için tercih edilen volatil anesteziklerden biridir. Desfluran kan gazı çözünürlüğü düşük olduğu için hızlı derlenme sağlar. Minimum alveolar konsantrasyon, anestezik potensin bir göstergesidir. Volatil anestezikler doza bağlı olarak kan basıncını düşürebilir.

# Nöromüsküler Blokörler

Süksinilkolin hızlı etkili depolarizan nöromüsküler blokördür. Rokolokyum ve vekuronyum nondepolarizan blokörlerdir. Nöromüsküler blokajın derinliği sinir stimülatörü ile izlenebilir. Rezidüel blokaj postoperatif solunum komplikasyonlarını artırabilir.
"""

SKILLS = [
    ("Temel Anestezi Kavramları", "temel", "Anestezi pratiğinin temel kavramları", None),
    ("Solunum ve Havayolu", "fizyoloji", "Solunum fizyolojisi ve havayolu yönetimi", "Temel Anestezi Kavramları"),
    ("İntravenöz Anestezikler", "farmakoloji", "İV anestezik ajanlar ve klinik kullanımı", "Temel Anestezi Kavramları"),
    ("İnhalasyon Anestezikleri", "farmakoloji", "Volatil ajanlar ve MAC kavramı", "Temel Anestezi Kavramları"),
    ("Nöromüsküler Blokörler", "farmakoloji", "Kas gevşeticiler ve izlem", "Solunum ve Havayolu"),
    ("Anestezi Komplikasyonları", "klinik", "Perioperatif komplikasyonların yönetimi", "İntravenöz Anestezikler"),
]

USERS = [
    ("admin@medspaced.local", "Admin1234!", "Sistem Yöneticisi", "admin"),
    ("reviewer@medspaced.local", "Reviewer1234!", "Uzman Eğitmen", "reviewer"),
    ("student@medspaced.local", "Student1234!", "Örnek Öğrenci", "student"),
]


def seed_users(db) -> None:
    for email, password, full_name, role in USERS:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"  = kullanıcı mevcut: {email}")
            continue
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
            )
        )
        print(f"  + kullanıcı: {email} ({role})")
    db.commit()


def seed_skills(db) -> dict[str, SkillNode]:
    nodes: dict[str, SkillNode] = {}
    for title, category, description, _ in SKILLS:
        node = db.scalar(select(SkillNode).where(SkillNode.title == title))
        if node is None:
            node = SkillNode(title=title, category=category, description=description)
            db.add(node)
            db.flush()
            print(f"  + skill: {title}")
        nodes[title] = node
    db.commit()

    for title, _, _, prerequisite_title in SKILLS:
        if not prerequisite_title:
            continue
        node = nodes[title]
        prerequisite = nodes[prerequisite_title]
        exists = db.scalar(
            select(SkillPrerequisite).where(
                SkillPrerequisite.skill_id == node.id,
                SkillPrerequisite.prerequisite_id == prerequisite.id,
            )
        )
        if exists is None:
            db.add(SkillPrerequisite(skill_id=node.id, prerequisite_id=prerequisite.id))
    db.commit()
    return nodes


def seed_demo_content(db, nodes: dict[str, SkillNode]) -> None:
    existing = db.scalar(select(ContentFile).where(ContentFile.filename == DEMO_FILENAME))
    if existing is not None:
        print("  = demo içerik mevcut, atlandı")
        return

    reviewer = db.scalar(select(User).where(User.email == "reviewer@medspaced.local"))
    target = Path("var/storage") / DEMO_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(DEMO_CONTENT, encoding="utf-8")

    content_file = ContentFile(
        uploaded_by=reviewer.id if reviewer else None,
        filename=DEMO_FILENAME,
        mime_type="text/markdown",
        size_bytes=len(DEMO_CONTENT.encode("utf-8")),
        checksum="seed-demo",
        storage_path=str(target),
        status="uploaded",
    )
    db.add(content_file)
    db.commit()
    db.refresh(content_file)
    result = process_file(db, content_file)
    print(f"  + demo içerik işlendi: {result['chunks']} chunk")

    skill = nodes["Temel Anestezi Kavramları"]
    generation = generate_for_file(
        db,
        file_id=content_file.id,
        skill_id=skill.id,
        exercise_types=["mcq", "cloze"],
        max_chunks=6,
    )
    print(
        "  + demo sorular üretildi: "
        f"{generation['exercises_created']} soru "
        f"({generation['skipped']} atlandı)"
    )

    exercises = list(
        db.scalars(select(Exercise).where(Exercise.status == "under_review"))
    )
    for exercise in exercises:
        exercise.status = "approved"
        exercise.reviewed_by = reviewer.id if reviewer else None
        exercise.reviewed_at = utcnow()
        exercise.difficulty_at_approval = exercise.difficulty
    db.commit()
    print(f"  + {len(exercises)} soru onaylandı")


def main() -> None:
    print("MedSpaced seed başlıyor...")
    init_db()
    db = SessionLocal()
    try:
        print("[1/3] Kullanıcılar")
        seed_users(db)
        print("[2/3] Skill grafiği")
        nodes = seed_skills(db)
        print("[3/3] Demo içerik ve sorular")
        seed_demo_content(db, nodes)
    finally:
        db.close()
    print("\nHazır. Giriş bilgileri:")
    for email, password, _, role in USERS:
        print(f"  {role:9s} {email} / {password}")


if __name__ == "__main__":
    main()
