"""
Shared Jinja runtime configuration.

Development keeps template hot reload enabled. Production disables reload and
uses a filesystem bytecode cache when CASEHUB_ENV=production or DEBUG=false.

UI Remake: instala um ChoiceLoader que prefere `app/X/Y.html` quando existir
sobre `X/Y.html` legacy. Isso garante que TODOS os handlers de routes/*.py
que fazem templates.TemplateResponse('clients/list.html', ctx) automaticamente
renderizem o wrapper novo `app/clients/list.html` que envolve o body legacy
dentro do shell novo (topbar + bottom-nav + tabs desktop).

O wrapper preserva o contexto, JS, fields, modais — só envolve o body. Para
templates onde o app/* é uma versão totalmente reescrita (rich), o handler
permanece como antes. Para os ~170 wrappers automáticos gerados em batch,
funcionalidade legacy continua intacta.
"""
import os
import logging
from typing import Optional

from jinja2 import FileSystemBytecodeCache, ChoiceLoader, FileSystemLoader, TemplateNotFound

from config import settings


logger = logging.getLogger(__name__)
PRODUCTION_ENVS = {"production", "prod"}


def is_production_env() -> bool:
    env_name = (settings.CASEHUB_ENV or "").strip().lower()
    return env_name in PRODUCTION_ENVS or settings.DEBUG is False


class AppPreferLoader(FileSystemLoader):
    """Custom loader: ao receber 'X/Y.html', tenta 'app/X/Y.html' primeiro.

    Se app/X/Y.html existe, retorna ele (novo shell wrapper). Senão, retorna
    o legacy X/Y.html. Templates que já começam com 'app/' são passados direto.
    """
    def get_source(self, environment, template):
        # Pass-through: templates que já são app/*, partials/*, base.html, etc
        if (
            template.startswith('app/') or
            template.startswith('partials/') or
            template.startswith('_archive/') or
            template in ('base.html', 'landing.html', 'login.html', 'forgot_password.html', 'base_minimal.html')
        ):
            return super().get_source(environment, template)
        # Try app/X/Y.html first
        app_path = f'app/{template}'
        try:
            return super().get_source(environment, app_path)
        except TemplateNotFound:
            # Fall through to legacy template
            return super().get_source(environment, template)


def configure_jinja_templates(
    templates,
    *,
    production: Optional[bool] = None,
    cache_dir: Optional[str] = None,
):
    """
    Apply the same runtime policy to every Jinja2Templates instance.

    Args:
        templates: fastapi.templating.Jinja2Templates instance.
        production: Optional override for tests.
        cache_dir: Optional bytecode cache directory override.
    """
    use_production = is_production_env() if production is None else production
    templates.env.auto_reload = not use_production

    if use_production:
        bytecode_dir = cache_dir or settings.JINJA_BYTECODE_CACHE_DIR
        os.makedirs(bytecode_dir, exist_ok=True)
        templates.env.bytecode_cache = FileSystemBytecodeCache(bytecode_dir)
    else:
        templates.env.bytecode_cache = None

    # Install the prefer-app loader. Wrap the existing loader to preserve
    # any custom search paths the original might have.
    original = templates.env.loader
    search_paths = []
    if isinstance(original, FileSystemLoader):
        search_paths = list(original.searchpath)
    elif isinstance(original, ChoiceLoader):
        for sub in original.loaders:
            if isinstance(sub, FileSystemLoader):
                search_paths.extend(sub.searchpath)
    if not search_paths:
        search_paths = ['templates']
    templates.env.loader = AppPreferLoader(search_paths)
    logger.info(
        "[ui-remake] AppPreferLoader installed; app/X/Y.html preferred over X/Y.html"
    )

    return templates
