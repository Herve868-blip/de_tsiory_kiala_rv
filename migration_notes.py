import pandas as pd
import psycopg2
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# CONFIG - MODIFIEZ CES PARAMETRES SI BESOIN
# ============================================================
EXCEL_PATH = os.path.join(os.path.dirname(__file__), 'de_inscae', 'Gest°_Notes_S°Août 2025.xls')
SHEET_NAME = 'Base_All'

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'Herv',        # Nom de la base Odoo
    'user': 'odoo',          # Utilisateur PostgreSQL
    'password': 'odoo',      # Mot de passe PostgreSQL
}

# Noms des tables (adapter si vous utilisez un schema Odoo different)
TABLE_ETUDIANTS = 'gest_notes_etudiants'
TABLE_MATIERES  = 'gest_notes_matieres'
TABLE_NOTES     = 'gest_notes_notes'

# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================
def connect_db():
    """Connexion a PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        print("  Connexion a PostgreSQL reussie!")
        return conn
    except Exception as e:
        print(f"  ERREUR de connexion: {e}")
        sys.exit(1)


def create_tables_if_needed(conn):
    """Creer les tables si elles n'existent pas"""
    cursor = conn.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_ETUDIANTS} (
            id               SERIAL PRIMARY KEY,
            matricule        VARCHAR(20)  NOT NULL UNIQUE,
            nom_prenom       VARCHAR(255) NOT NULL,
            nb_matieres      INTEGER      DEFAULT 0,
            moyenne_generale DECIMAL(5,2) DEFAULT NULL,
            observation      VARCHAR(50)  DEFAULT NULL,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_MATIERES} (
            id   SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL UNIQUE
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NOTES} (
            id                 SERIAL PRIMARY KEY,
            etudiant_id        INTEGER       NOT NULL,
            matiere_id         INTEGER       NOT NULL,
            moyenne            DECIMAL(5,2)  NOT NULL,
            credits            DECIMAL(3,1)  NOT NULL,
            moyenne_ponderee   DECIMAL(6,2)  NOT NULL,
            decision           VARCHAR(30)   NOT NULL,
            session            VARCHAR(50)   DEFAULT 'S Aout 2025',
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (etudiant_id) REFERENCES {TABLE_ETUDIANTS}(id),
            FOREIGN KEY (matiere_id)  REFERENCES {TABLE_MATIERES}(id),
            UNIQUE (etudiant_id, matiere_id, session)
        )
    """)

    conn.commit()
    print("  Tables creees/verifiees avec succes!")


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================
def main():
    print("=" * 60)
    print("MIGRATION EXCEL -> POSTGRESQL (ODOO)")
    print("Session Aout 2025 - INScae")
    print("=" * 60)

    # 1) Lire le fichier Excel
    print("\n[1/4] Lecture du fichier Excel...")
    if not os.path.exists(EXCEL_PATH):
        print(f"  ERREUR: Fichier non trouve: {EXCEL_PATH}")
        sys.exit(1)

    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        print(f"  {len(df)} lignes, {len(df.columns)} colonnes")
    except Exception as e:
        print(f"  ERREUR de lecture: {e}")
        sys.exit(1)

    # 2) Connexion et creation des tables
    print("\n[2/4] Connexion a PostgreSQL...")
    conn = connect_db()
    create_tables_if_needed(conn)
    cursor = conn.cursor()

    # 3) Inserer les matieres
    print("\n[3/4] Insertion des matieres...")
    mat_cols_indices = [5, 10, 15, 20, 25, 30]  # Indices des colonnes Mat1..Mat6
    all_subjects = set()
    for col_idx in mat_cols_indices:
        if col_idx < len(df.columns):
            vals = df.iloc[:, col_idx].dropna().unique()
            all_subjects.update(vals)

    # Recuperer les matieres deja existantes
    cursor.execute(f"SELECT code FROM {TABLE_MATIERES}")
    existing = {row[0] for row in cursor.fetchall()}

    matiere_id_map = {}
    nb_new = 0
    for subject in sorted(all_subjects):
        subject_str = str(subject).strip()
        if subject_str in existing:
            cursor.execute(f"SELECT id FROM {TABLE_MATIERES} WHERE code = %s", (subject_str,))
            matiere_id_map[subject_str] = cursor.fetchone()[0]
        else:
            cursor.execute(f"INSERT INTO {TABLE_MATIERES} (code) VALUES (%s) RETURNING id", (subject_str,))
            matiere_id_map[subject_str] = cursor.fetchone()[0]
            existing.add(subject_str)
            nb_new += 1

    conn.commit()
    print(f"  {len(matiere_id_map)} matieres au total ({nb_new} nouvelles)")

    # 4) Inserer les etudiants et leurs notes
    print("\n[4/4] Insertion des etudiants et notes...")
    nb_etudiants = 0
    nb_notes = 0
    nb_skip = 0

    for index, row in df.iterrows():
        matricule = row.iloc[2]   # NMatricule
        nom       = row.iloc[3]   # Nom et Prenoms
        nb_mat    = row.iloc[4]   # NbMat

        # Sauter les lignes vides
        if pd.isna(matricule) or pd.isna(nom):
            nb_skip += 1
            continue

        matricule = str(matricule).strip()
        nom       = str(nom).strip()

        # Inserer l'etudiant (ignorer si doublon)
        try:
            cursor.execute(
                f"INSERT INTO {TABLE_ETUDIANTS} (matricule, nom_prenom, nb_matieres) VALUES (%s, %s, %s) RETURNING id",
                (matricule, nom, int(nb_mat) if not pd.isna(nb_mat) else 0)
            )
            etudiant_id = cursor.fetchone()[0]
            nb_etudiants += 1
        except Exception:
            # Etudiant deja existe -> recuperer son id
            cursor.execute(f"SELECT id FROM {TABLE_ETUDIANTS} WHERE matricule = %s", (matricule,))
            result = cursor.fetchone()
            if result:
                etudiant_id = result[0]
            else:
                nb_skip += 1
                continue

        # Parcourir les 6 matieres possibles
        for i in range(1, 7):
            base = 4 + (i - 1) * 5

            mat_code    = row.iloc[base + 1]   # Mat{i}
            moyenne     = row.iloc[base + 2]   # Moy_Mat{i}
            credits     = row.iloc[base + 3]   # Ce
            moy_pond    = row.iloc[base + 4]   # MoyPd_Mat{i}
            decision    = row.iloc[base + 5]   # Dese_Mat{i}

            # Si pas de matiere pour cette colonne, on saute
            if pd.isna(mat_code) or str(mat_code).strip() == 'nan':
                continue

            mat_code = str(mat_code).strip()

            # Verifier que la matiere existe dans le map
            if mat_code not in matiere_id_map:
                print(f"  ! Matiere inconnue: {mat_code} (ligne {index})")
                continue

            # Sauter si les notes sont NaN
            if pd.isna(moyenne) or pd.isna(credits) or pd.isna(moy_pond):
                continue

            dec_str = str(decision).strip() if not pd.isna(decision) else 'Non evalue'

            try:
                cursor.execute(
                    f"""INSERT INTO {TABLE_NOTES} (etudiant_id, matiere_id, moyenne, credits, moyenne_ponderee, decision)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (etudiant_id, matiere_id_map[mat_code],
                     float(moyenne), float(credits), float(moy_pond), dec_str)
                )
                nb_notes += 1
            except Exception:
                # Note deja existante pour cette matiere/etudiant
                pass

        # Mettre a jour la moyenne generale et observation de l'etudiant
        moy_gen  = row.iloc[37]  # MoyPd /20
        obs      = row.iloc[40]  # Observation
        if not pd.isna(moy_gen):
            cursor.execute(
                f"UPDATE {TABLE_ETUDIANTS} SET moyenne_generale = %s, observation = %s WHERE id = %s",
                (float(moy_gen), str(obs) if not pd.isna(obs) else None, etudiant_id)
            )

    conn.commit()

    print("\n" + "=" * 60)
    print("RESUMAT DE LA MIGRATION")
    print("=" * 60)
    print(f"  Etudiants inseres  : {nb_etudiants}")
    print(f"  Notes inserees     : {nb_notes}")
    print(f"  Lignes sautees     : {nb_skip}")
    print(f"  Matieres en base   : {len(matiere_id_map)}")
    print("=" * 60)

    cursor.close()
    conn.close()
    print("\nMigration terminee avec succes!")


if __name__ == '__main__':
    main()
