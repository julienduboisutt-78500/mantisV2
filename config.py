import json
import os
from pathlib import Path

CONFIG_FILE = Path(os.getcwd()) / ".app_config.json"

def detect_local_onedrive_folder() -> Path:
    """Détecte automatiquement le dossier racine OneDrive Entreprise sur la machine."""
    od = os.environ.get("OneDriveCommercial") or os.environ.get("OneDrive")
    if od and os.path.exists(od):
        return Path(od)
    
    # Vérification dossier utilisateur standard
    candidate_cegid = Path.home() / "OneDrive - CEGID"
    if candidate_cegid.exists():
        return candidate_cegid
    
    candidate_perso = Path.home() / "OneDrive"
    if candidate_perso.exists():
        return candidate_perso
        
    return Path(os.getcwd())

def get_config_data() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def get_sharepoint_url() -> str:
    """Renvoie l'URL SharePoint configurée si disponible."""
    return get_config_data().get("sharepoint_url", "")

def get_storage_path() -> Path:
    """Renvoie le chemin configuré pour le stockage local des données OneDrive."""
    cfg = get_config_data()
    configured = cfg.get("onedrive_path")
    
    # Si on est sur Linux/Streamlit Cloud mais qu'un chemin Windows C:\ est configuré, basculer sur stockage local
    if configured and os.name != "nt" and ("\\" in configured or ":" in configured):
        configured = None

    if configured:
        try:
            p = Path(configured)
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    # Par défaut : sous-dossier dans le OneDrive détecté ou dans le répertoire de travail
    od_root = detect_local_onedrive_folder()
    if "OneDrive" in str(od_root):
        default_p = od_root / "MantisV2_Storage"
    else:
        default_p = Path(os.getcwd()) / "onedrive_storage"
        
    default_p.mkdir(parents=True, exist_ok=True)
    return default_p

def set_storage_path(new_input: str) -> tuple[bool, str, Path]:
    """
    Met à jour la configuration avec soit une URL SharePoint (https://...),
    soit un chemin de dossier Windows local.
    """
    new_input = new_input.strip()
    if not new_input:
        return False, "Veuillez renseigner un chemin ou un lien SharePoint valide.", get_storage_path()

    cfg = get_config_data()

    # CAS 1 : Lien Web SharePoint / OneDrive (ex: https://cegidgroup-my.sharepoint.com/:f:/g/personal/...)
    if new_input.lower().startswith("http://") or new_input.lower().startswith("https://"):
        try:
            od_root = detect_local_onedrive_folder()
            # Créer un dossier dédié dans le OneDrive local synchronisé
            local_storage_dir = od_root / "MantisV2_Storage"
            local_storage_dir.mkdir(parents=True, exist_ok=True)

            # Test écriture
            test_file = local_storage_dir / ".write_test"
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("test")
            test_file.unlink()

            cfg["sharepoint_url"] = new_input
            cfg["onedrive_path"] = str(local_storage_dir)

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

            msg = (
                f"Lien SharePoint enregistré avec succès !\n\n"
                f"Les données sont stockées dans votre dossier local synchronisé :\n"
                f"`{local_storage_dir}`\n\n"
                f"Le client OneDrive de votre PC assure la synchronisation automatique en continu vers votre espace SharePoint en ligne."
            )
            return True, msg, local_storage_dir
        except Exception as e:
            return False, f"Erreur lors de l'association au dossier OneDrive local : {e}", get_storage_path()

    # CAS 2 : Chemin local Windows (ex: C:\Users\...\OneDrive - CEGID\...)
    try:
        p = Path(new_input).resolve()
        p.mkdir(parents=True, exist_ok=True)
        # Test écriture
        test_file = p / ".write_test"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        test_file.unlink()

        cfg["onedrive_path"] = str(p)
        # Conserver l'URL SharePoint si déjà présente

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        return True, f"Chemin configuré avec succès : `{p}`", p
    except Exception as e:
        return False, f"Erreur lors de la configuration du chemin : {e}", get_storage_path()

def get_db_path() -> Path:
    return get_storage_path() / "ticketing.db"

def get_attachments_dir() -> Path:
    attach_dir = get_storage_path() / "attachments"
    attach_dir.mkdir(parents=True, exist_ok=True)
    return attach_dir
