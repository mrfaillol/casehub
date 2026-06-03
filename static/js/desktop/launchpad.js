// Initialize on load
function initDesktopLaunchpad() {
    // Only run if desktop mode is active
    if (!document.body.classList.contains('desktop')) return;

    const launchpad = document.getElementById('osLaunchpad');
    const launchpadGrid = document.getElementById('launchpadGrid');
    const searchInput = document.getElementById('launchpadSearch');
    if (!launchpad || !launchpadGrid) return;

    // 1. Add Launchpad Button to Dock
    // Prefer <ul> container (so <li> fica válido); fallback cria <ul> wrapper.
    let sidebarItemsContainer = document.querySelector('.sidebar ul.nav, .sidebar .nav.flex-column');
    const sidebarRoot = document.querySelector('.sidebar');
    if (!sidebarItemsContainer && sidebarRoot) {
        // Wrap children em <ul> se não houver nav list — mantém <li> semanticamente válido
        sidebarItemsContainer = document.createElement('ul');
        sidebarItemsContainer.className = 'nav flex-column';
        sidebarRoot.insertBefore(sidebarItemsContainer, sidebarRoot.firstChild);
    }
    if (sidebarItemsContainer) {
        const launchpadLi = document.createElement('li');
        launchpadLi.className = 'nav-item';

        const launchpadBtn = document.createElement('a');
        launchpadBtn.className = 'nav-link';
        launchpadBtn.href = '#';
        launchpadBtn.id = 'desktopLaunchpadBtn';
        launchpadBtn.dataset.tooltip = 'Launchpad';
        launchpadBtn.setAttribute('aria-label', 'Abrir Launchpad');
        launchpadBtn.setAttribute('title', 'Launchpad');
        launchpadBtn.innerHTML = '<i class="fas fa-th" aria-hidden="true"></i>';

        launchpadBtn.addEventListener('click', (e) => {
            e.preventDefault();
            toggleLaunchpad();
        });

        launchpadLi.appendChild(launchpadBtn);
        sidebarItemsContainer.insertBefore(launchpadLi, sidebarItemsContainer.firstChild);
    }

    // 2. Populate Launchpad Grid
    // Extract all unique apps from sidebar
    const allLinks = document.querySelectorAll('.sidebar .nav-link');
    const appSet = new Set();
    const apps = [];

    allLinks.forEach(link => {
        // Skip the launchpad button itself
        if (link.id === 'desktopLaunchpadBtn') return;
        
        const href = link.getAttribute('href');
        if (!href || href === '#' || appSet.has(href)) return;
        appSet.add(href);

        const iconEl = link.querySelector('i');
        const iconClass = iconEl ? iconEl.className : 'fas fa-cube';
        
        // Extract title from tooltip or text
        let title = link.dataset.tooltip || (link.textContent || '').trim();
        if (!title) return;

        apps.push({ href, iconClass, title });
    });

    // Generate Grid DOM
    apps.forEach((app, index) => {
        const appLink = document.createElement('a');
        appLink.className = 'launchpad-app';
        appLink.href = app.href;
        appLink.dataset.index = index;

        appLink.innerHTML = `
            <div class="launchpad-app-icon">
                <i class="${app.iconClass}"></i>
            </div>
            <div class="launchpad-app-title">${app.title}</div>
        `;

        appLink.addEventListener('click', (e) => {
            if (window.osWindowManager) {
                e.preventDefault();
                window.osWindowManager.launchApp(app.href, app.title, app.iconClass);
                closeLaunchpad();
            }
        });

        launchpadGrid.appendChild(appLink);
    });

    // 3. Toggle Logic
    let isOpen = false;
    let animationStaggerTimeouts = [];

    function toggleLaunchpad() {
        if (isOpen) {
            closeLaunchpad();
        } else {
            openLaunchpad();
        }
    }

    function openLaunchpad() {
        isOpen = true;
        launchpad.classList.add('visible');
        if (searchInput) {
            searchInput.value = '';
            searchInput.focus();
            filterApps(''); // show all
        }

        // Animate icons sequentially for that classic OS popup feel
        const appElements = launchpadGrid.querySelectorAll('.launchpad-app');
        appElements.forEach(el => el.classList.remove('animate-in')); // reset

        animationStaggerTimeouts.forEach(clearTimeout);
        animationStaggerTimeouts = [];

        appElements.forEach((el, index) => {
            const timeout = setTimeout(() => {
                el.classList.add('animate-in');
            }, 100 + (index * 20));
            animationStaggerTimeouts.push(timeout);
        });
    }

    function closeLaunchpad() {
        isOpen = false;
        launchpad.classList.remove('visible');
        searchInput.blur();
        
        // Let the CSS transition handle the exit for all simultaneously
        const appElements = launchpadGrid.querySelectorAll('.launchpad-app');
        appElements.forEach(el => el.classList.remove('animate-in'));
    }

    // 4. Close triggers
    launchpad.addEventListener('click', (e) => {
        // If clicking the background (not search bar or apps)
        if (e.target === launchpad || e.target === launchpadGrid) {
            closeLaunchpad();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && isOpen) {
            closeLaunchpad();
        }
    });

    // 5. Search Logic
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            filterApps(e.target.value);
        });
    }

    function filterApps(query) {
        query = query.toLowerCase().trim();
        const appElements = launchpadGrid.querySelectorAll('.launchpad-app');
        
        appElements.forEach(el => {
            const title = el.querySelector('.launchpad-app-title').textContent.toLowerCase();
            if (title.includes(query)) {
                el.style.display = 'flex';
                // ensure it has animate-in if already open
                if (isOpen) el.classList.add('animate-in');
            } else {
                el.style.display = 'none';
                el.classList.remove('animate-in');
            }
        });
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesktopLaunchpad);
} else {
    initDesktopLaunchpad();
}
