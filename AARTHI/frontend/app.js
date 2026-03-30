
const stocksData = [
    {
        symbol: "RELIANCE",
        name: "Reliance Industries",
        price: 1348.00,
        change: +2.34,
        changePercent: +0.17,
        logo: "RIL",
        chartData: [1320, 1335, 1328, 1342, 1338, 1345, 1340, 1348]
    },
    {
        symbol: "TCS",
        name: "Tata Consultancy Services",
        price: 2389.80,
        change: +18.45,
        changePercent: +0.78,
        logo: "TCS",
        chartData: [2350, 2365, 2358, 2374, 2380, 2372, 2385, 2390]
    },
    {
        symbol: "HDFCBANK",
        name: "HDFC Bank",
        price: 756.20,
        change: -3.10,
        changePercent: -0.41,
        logo: "HDB",
        chartData: [762, 758, 760, 755, 757, 753, 758, 756]
    },
    {
        symbol: "INFY",
        name: "Infosys Limited",
        price: 1269.70,
        change: +12.30,
        changePercent: +0.98,
        logo: "INF",
        chartData: [1250, 1258, 1255, 1262, 1268, 1260, 1265, 1270]
    },
    {
        symbol: "BHARTIARTL",
        name: "Bharti Airtel",
        price: 1844.00,
        change: +24.50,
        changePercent: +1.35,
        logo: "AIR",
        chartData: [1800, 1815, 1808, 1825, 1830, 1838, 1835, 1844]
    },
    {
        symbol: "ICICIBANK",
        name: "ICICI Bank",
        price: 1234.00,
        change: +8.20,
        changePercent: +0.67,
        logo: "ICI",
        chartData: [1218, 1225, 1220, 1228, 1230, 1226, 1232, 1234]
    },
    {
        symbol: "BAJFINANCE",
        name: "Bajaj Finance",
        price: 844.00,
        change: -5.60,
        changePercent: -0.66,
        logo: "BAJ",
        chartData: [855, 850, 852, 848, 846, 850, 845, 844]
    },
    {
        symbol: "HUL",
        name: "Hindustan Unilever",
        price: 2074.00,
        change: +15.80,
        changePercent: +0.77,
        logo: "HUL",
        chartData: [2045, 2055, 2050, 2060, 2065, 2058, 2068, 2074]
    },
    {
        symbol: "ITC",
        name: "ITC Limited",
        price: 295.00,
        change: +1.85,
        changePercent: +0.63,
        logo: "ITC",
        chartData: [290, 292, 291, 293, 292, 294, 293, 295]
    }
];

// ─── Three.js Globe Setup ─────────────────────────────
let scene, camera, renderer, globe, clouds, atmosphere;
let scrollProgress = 0;
const globeContainer = document.getElementById('globe-container');

// Mumbai coordinates (lat, lon) -> spherical
const MUMBAI_LAT = 19.076; // degrees
const MUMBAI_LON = 72.8777; // degrees

function initGlobe() {
    // Scene
    scene = new THREE.Scene();

    // Camera
    camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 0, 5);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    globeContainer.appendChild(renderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x404060, 0.6);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 1.4);
    sunLight.position.set(5, 3, 5);
    scene.add(sunLight);

    const rimLight = new THREE.DirectionalLight(0x4f8cff, 0.4);
    rimLight.position.set(-5, -2, -5);
    scene.add(rimLight);

    // Earth sphere — load real NASA texture with fallback
    createEarth();

    // Stars
    createStars();

    // Handle resize
    window.addEventListener('resize', onResize);

    // Start animation loop
    animate();
}

function createEarth() {
    const earthGeometry = new THREE.SphereGeometry(1.5, 64, 64);
    const loader = new THREE.TextureLoader();

    // Use NASA/Solar System Scope texture (CC-BY-4.0)
    const textureUrl = 'https://unpkg.com/three-globe@2.41.12/example/img/earth-blue-marble.jpg';

    // Create globe with a temporary dark material first (instant feedback)
    const earthMaterial = new THREE.MeshPhongMaterial({
        color: 0x0d2137,
        shininess: 25,
        specular: new THREE.Color(0x1a3050),
    });

    globe = new THREE.Mesh(earthGeometry, earthMaterial);
    scene.add(globe);

    // Load real texture
    loader.load(
        textureUrl,
        (texture) => {
            globe.material.map = texture;
            globe.material.color.set(0xffffff);
            globe.material.needsUpdate = true;
        },
        undefined,
        () => {
            // Fallback: try another URL
            loader.load(
                'https://cdn.jsdelivr.net/npm/three-globe@2.41.12/example/img/earth-blue-marble.jpg',
                (texture) => {
                    globe.material.map = texture;
                    globe.material.color.set(0xffffff);
                    globe.material.needsUpdate = true;
                },
                undefined,
                () => {
                    // Final fallback: procedural dark-themed earth
                    createProceduralTexture(globe);
                }
            );
        }
    );

    // Atmosphere glow
    const atmosphereGeometry = new THREE.SphereGeometry(1.58, 64, 64);
    const atmosphereMaterial = new THREE.ShaderMaterial({
        vertexShader: `
            varying vec3 vNormal;
            void main() {
                vNormal = normalize(normalMatrix * normal);
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            varying vec3 vNormal;
            void main() {
                float intensity = pow(0.65 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.5);
                gl_FragColor = vec4(0.31, 0.55, 1.0, 1.0) * intensity;
            }
        `,
        blending: THREE.AdditiveBlending,
        side: THREE.BackSide,
        transparent: true,
    });

    atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphere);

    // Cloud layer
    const cloudCanvas = document.createElement('canvas');
    cloudCanvas.width = 1024;
    cloudCanvas.height = 512;
    const cloudCtx = cloudCanvas.getContext('2d');
    cloudCtx.fillStyle = 'rgba(0, 0, 0, 0)';
    cloudCtx.fillRect(0, 0, 1024, 512);
    
    // Wispy clouds
    cloudCtx.fillStyle = 'rgba(255, 255, 255, 0.06)';
    for (let i = 0; i < 200; i++) {
        const x = Math.random() * 1024;
        const y = Math.random() * 512;
        const w = Math.random() * 60 + 10;
        const h = Math.random() * 12 + 3;
        cloudCtx.beginPath();
        cloudCtx.ellipse(x, y, w, h, Math.random() * Math.PI, 0, Math.PI * 2);
        cloudCtx.fill();
    }
    
    const cloudTexture = new THREE.CanvasTexture(cloudCanvas);
    cloudTexture.wrapS = THREE.RepeatWrapping;
    
    const cloudGeometry = new THREE.SphereGeometry(1.52, 64, 64);
    const cloudMaterial = new THREE.MeshPhongMaterial({
        map: cloudTexture,
        transparent: true,
        opacity: 0.3,
        depthWrite: false,
    });

    clouds = new THREE.Mesh(cloudGeometry, cloudMaterial);
    scene.add(clouds);

    // Initial rotation: show Americas/Atlantic facing camera
    const initialLon = 80; // degrees — higher positive = more Americas visible
    globe.rotation.y = THREE.MathUtils.degToRad(initialLon);
    clouds.rotation.y = THREE.MathUtils.degToRad(initialLon);
}

// Fallback procedural texture if CDN textures fail
function createProceduralTexture(globeMesh) {
    const earthCanvas = document.createElement('canvas');
    earthCanvas.width = 2048;
    earthCanvas.height = 1024;
    const ctx = earthCanvas.getContext('2d');
    
    // Deep ocean gradient
    const oceanGrad = ctx.createLinearGradient(0, 0, 0, 1024);
    oceanGrad.addColorStop(0, '#061224');
    oceanGrad.addColorStop(0.3, '#0a1e3a');
    oceanGrad.addColorStop(0.5, '#0d2540');
    oceanGrad.addColorStop(0.7, '#0a1e3a');
    oceanGrad.addColorStop(1, '#061224');
    ctx.fillStyle = oceanGrad;
    ctx.fillRect(0, 0, 2048, 1024);

    // Simplified landmasses with glow
    ctx.fillStyle = '#143028';
    ctx.strokeStyle = '#1a4035';
    ctx.lineWidth = 2;

    // Continents (simplified outlines)
    const continents = [
        // Africa
        [[1050,320],[1080,300],[1110,310],[1130,350],[1140,400],[1140,450],[1130,500],[1110,550],[1090,580],[1060,590],[1040,560],[1030,510],[1020,450],[1015,400],[1025,350]],
        // Europe
        [[995,230],[1020,215],[1060,220],[1100,230],[1105,250],[1090,265],[1060,275],[1030,280],[1000,270],[990,250]],
        // Asia
        [[1120,210],[1170,195],[1230,195],[1300,210],[1370,230],[1430,260],[1450,290],[1430,330],[1400,370],[1370,400],[1340,400],[1300,370],[1260,350],[1230,360],[1200,370],[1170,350],[1140,330],[1120,280],[1115,240]],
        // India
        [[1240,355],[1265,345],[1285,360],[1290,390],[1280,415],[1268,440],[1258,460],[1248,455],[1238,435],[1232,410],[1230,380]],
        // North America
        [[350,190],[390,175],[440,185],[490,210],[510,245],[515,280],[505,320],[480,345],[450,355],[420,340],[390,310],[365,280],[345,245],[340,220]],
        // South America
        [[495,420],[520,412],[540,425],[555,455],[558,500],[550,550],[535,600],[515,650],[495,670],[480,650],[475,610],[478,560],[482,510],[488,460]],
        // Australia
        [[1460,520],[1495,510],[1530,520],[1545,545],[1535,575],[1510,585],[1480,575],[1460,555],[1455,535]],
    ];

    continents.forEach(pts => {
        if (pts.length < 3) return;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
            const next = pts[(i + 1) % pts.length];
            const xc = (pts[i][0] + next[0]) / 2;
            const yc = (pts[i][1] + next[1]) / 2;
            ctx.quadraticCurveTo(pts[i][0], pts[i][1], xc, yc);
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
    });

    // Mumbai marker
    const mumbaiX = Math.round((MUMBAI_LON / 360 + 0.5) * 2048);
    const mumbaiY = Math.round((0.5 - MUMBAI_LAT / 180) * 1024);
    const glowGrad = ctx.createRadialGradient(mumbaiX, mumbaiY, 0, mumbaiX, mumbaiY, 25);
    glowGrad.addColorStop(0, 'rgba(79, 140, 255, 0.9)');
    glowGrad.addColorStop(0.4, 'rgba(79, 140, 255, 0.3)');
    glowGrad.addColorStop(1, 'rgba(79, 140, 255, 0)');
    ctx.fillStyle = glowGrad;
    ctx.fillRect(mumbaiX - 25, mumbaiY - 25, 50, 50);
    ctx.beginPath();
    ctx.arc(mumbaiX, mumbaiY, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#4f8cff';
    ctx.fill();

    const texture = new THREE.CanvasTexture(earthCanvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;
    globeMesh.material.map = texture;
    globeMesh.material.color.set(0xffffff);
    globeMesh.material.needsUpdate = true;
}

function createStars() {
    const starsGeometry = new THREE.BufferGeometry();
    const starsCount = 3000;
    const positions = new Float32Array(starsCount * 3);
    const sizes = new Float32Array(starsCount);

    for (let i = 0; i < starsCount; i++) {
        const i3 = i * 3;
        const radius = 50 + Math.random() * 100;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.random() * Math.PI;
        positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
        positions[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
        positions[i3 + 2] = radius * Math.cos(phi);
        sizes[i] = Math.random() * 2 + 0.5;
    }

    starsGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    starsGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

    const starsMaterial = new THREE.PointsMaterial({
        color: 0xffffff,
        size: 0.15,
        transparent: true,
        opacity: 0.8,
        sizeAttenuation: true,
    });

    const stars = new THREE.Points(starsGeometry, starsMaterial);
    scene.add(stars);
}

function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

// ─── GSAP Scroll Animation ───────────────────────────
function initScrollAnimation() {
    gsap.registerPlugin(ScrollTrigger);

    // Target rotation to point at Mumbai (19.08°N, 72.88°E)
    // In Three.js SphereGeometry, the texture seam is at the back of the sphere.
    // rotation.y = 0 shows the center of the texture (around 0° longitude / Prime Meridian).
    // Positive rotation.y rotates the globe leftward (shows EAST on front face).
    // To face Mumbai (72.88°E), we need to rotate the globe by ~+72.88°.
    // But we must account for the initial rotation + any auto-rotation that happened.
    //
    // Since auto-rotation adds to globe.rotation.y continuously, we capture the current
    // value and compute a target based on that.

    // Record the actual starting rotation at the time scroll animation is initialized
    const startRotY = globe.rotation.y;
    const startRotX = globe.rotation.x;

    // To face Mumbai's longitude: the front of the sphere corresponds to the texture at
    // (rotation.y in degrees) longitude. So to show 72.88°E, we set rotation.y = -72.88° in rad.
    // But the texture may have a different zero-point. Let's compute it from the Blue Marble
    // texture where the center column (u=0.5) maps to rotation.y=0.
    // In standard Blue Marble, u=0 is at -180° lon and u=1 is at +180° lon.
    // The seam of the SphereGeometry along the +X axis maps to u=0.5 (0° lon) at rot.y=0.
    // To bring lon=72.88 to center: rot.y should be -(72.88 * PI/180).
    // However, observation shows the sign is REVERSED for this texture,
    // so we use positive rotation.
    
    // From empirical testing, the target that shows India correctly:
    const targetRotY = THREE.MathUtils.degToRad(-80);  
    const targetRotX = THREE.MathUtils.degToRad(6);

    // Main scroll timeline
    const tl = gsap.timeline({
        scrollTrigger: {
            trigger: '#hero-section',
            start: 'top top',
            end: 'bottom bottom',
            scrub: 1,
            onUpdate: (self) => {
                scrollProgress = self.progress;
            }
        }
    });

    // Phase 1: Fade out hero text (0 -> 0.2)
    tl.to('#hero-content', {
        opacity: 0,
        scale: 0.95,
        duration: 0.2,
    }, 0);

    tl.to('#scroll-indicator', {
        opacity: 0,
        duration: 0.1,
    }, 0);

    // Phase 2: Rotate globe to face India + zoom in (0.1 -> 0.8)
    tl.to(globe.rotation, {
        y: targetRotY,
        x: targetRotX,
        duration: 0.7,
        ease: 'power2.inOut',
    }, 0.1);

    tl.to(clouds.rotation, {
        y: targetRotY + 0.05,
        x: targetRotX,
        duration: 0.7,
        ease: 'power2.inOut',
    }, 0.1);

    // Zoom camera in — offset y slightly upward to center India's latitude
    tl.to(camera.position, {
        z: 2.6,
        y: 0.15,
        x: 0,
        duration: 0.7,
        ease: 'power2.inOut',
        onUpdate: () => camera.updateProjectionMatrix(),
    }, 0.15);

    // Phase 3: Show location label (0.5 -> 0.7)
    tl.fromTo('#location-label', {
        opacity: 0,
        y: 20,
    }, {
        opacity: 1,
        y: 0,
        duration: 0.15,
        onStart: () => {
            document.getElementById('location-label').classList.add('visible');
        }
    }, 0.5);

    // Phase 4: Fade everything as stocks section approaches (0.8 -> 1.0)
    tl.to('#location-label', {
        opacity: 0,
        duration: 0.15,
    }, 0.8);

    tl.to(camera.position, {
        z: 1.5,
        duration: 0.2,
        onUpdate: () => camera.updateProjectionMatrix(),
    }, 0.8);

    tl.to(globe.material, {
        opacity: 0,
        duration: 0.15,
    }, 0.85);

    // Pin the globe while we scroll through the hero
    ScrollTrigger.create({
        trigger: '#hero-section',
        start: 'top top',
        end: 'bottom bottom',
        pin: false,
    });

    // Unpin globe elements when stocks section arrives
    ScrollTrigger.create({
        trigger: '#stocks-section',
        start: 'top 80%',
        onEnter: () => {
            gsap.to('#globe-container', { opacity: 0, duration: 0.5 });
            gsap.to('.particle-canvas', { opacity: 0, duration: 0.5 });
        },
        onLeaveBack: () => {
            gsap.to('#globe-container', { opacity: 1, duration: 0.5 });
            gsap.to('.particle-canvas', { opacity: 1, duration: 0.5 });
        }
    });

    // Stocks section entrance animations
    ScrollTrigger.create({
        trigger: '#stocks-section',
        start: 'top 60%',
        onEnter: () => {
            gsap.fromTo('.stocks-header', {
                opacity: 0,
                y: 40,
            }, {
                opacity: 1,
                y: 0,
                duration: 0.8,
                ease: 'power3.out',
            });
        },
        once: true,
    });
}

// ─── Animation Loop ──────────────────────────────────
function animate() {
    requestAnimationFrame(animate);

    if (globe && scrollProgress < 0.05) {
        // Slow auto-rotation only when not scrolling
        globe.rotation.y += 0.0008;
        clouds.rotation.y += 0.001;
    }

    renderer.render(scene, camera);
}

// ─── Particle Background ─────────────────────────────
function initParticles() {
    const canvas = document.getElementById('particle-canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    const particleCount = 60;

    for (let i = 0; i < particleCount; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * 0.3,
            vy: (Math.random() - 0.5) * 0.3,
            radius: Math.random() * 1.5 + 0.5,
            opacity: Math.random() * 0.3 + 0.1,
        });
    }

    function drawParticles() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach((p, i) => {
            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0) p.x = canvas.width;
            if (p.x > canvas.width) p.x = 0;
            if (p.y < 0) p.y = canvas.height;
            if (p.y > canvas.height) p.y = 0;

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(96, 158, 69, ${p.opacity})`;
            ctx.fill();

            // Connect nearby particles
            for (let j = i + 1; j < particles.length; j++) {
                const dx = p.x - particles[j].x;
                const dy = p.y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(96, 158, 69, ${0.05 * (1 - dist / 150)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        });

        requestAnimationFrame(drawParticles);
    }

    drawParticles();

    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    });
}

// ─── Stock Cards ──────────────────────────────────────
function createMiniChart(data, isPositive) {
    const width = 240;
    const height = 48;
    const padding = 4;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    const points = data.map((v, i) => {
        const x = padding + (i / (data.length - 1)) * (width - padding * 2);
        const y = height - padding - ((v - min) / range) * (height - padding * 2);
        return `${x},${y}`;
    });

    const pathD = `M ${points.join(' L ')}`;
    const areaD = `${pathD} L ${width - padding},${height} L ${padding},${height} Z`;
    
    const color = isPositive ? '#34d399' : '#f87171';
    const gradientId = `grad_${Math.random().toString(36).substr(2, 9)}`;

    return `
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
            <defs>
                <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="${color}" stop-opacity="0.2"/>
                    <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
                </linearGradient>
            </defs>
            <path d="${areaD}" fill="url(#${gradientId})"/>
            <path d="${pathD}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    `;
}

function renderStockCards() {
    const grid = document.getElementById('stocks-grid');
    
    grid.innerHTML = stocksData.map((stock, index) => {
        const isPositive = stock.change >= 0;
        const changeClass = isPositive ? 'positive' : 'negative';
        const changePrefix = isPositive ? '+' : '';
        const chart = createMiniChart(stock.chartData, isPositive);

        return `
            <div class="stock-card" id="stock-${stock.symbol}" style="animation-delay: ${0.1 + index * 0.05}s">
                <div class="stock-card-header">
                    <div class="stock-info">
                        <span class="stock-symbol">${stock.symbol}</span>
                        <span class="stock-name">${stock.name}</span>
                    </div>
                    <div class="stock-logo">${stock.logo}</div>
                </div>
                <div class="stock-price-row">
                    <span class="stock-price">₹${stock.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                    <span class="stock-change ${changeClass}">${changePrefix}${stock.changePercent.toFixed(2)}%</span>
                </div>
                <div class="stock-chart">
                    ${chart}
                </div>
            </div>
        `;
    }).join('');
}

// ─── Simulate Live Price Updates ──────────────────────
function simulatePriceUpdates() {
    setInterval(() => {
        stocksData.forEach(stock => {
            // Small random price movement
            const movement = (Math.random() - 0.48) * stock.price * 0.001;
            stock.price = Math.round((stock.price + movement) * 100) / 100;
            stock.change = Math.round(movement * 100) / 100;
            stock.changePercent = Math.round((movement / stock.price) * 10000) / 100;
            
            // Update chart data
            stock.chartData.shift();
            stock.chartData.push(stock.price);
        });

        // Re-render cards with new data
        renderStockCards();
    }, 4000);
}

// ─── Initialize Everything ───────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initGlobe();
    initParticles();
    renderStockCards();
    
    // Wait a tick for Three.js to initialize
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            initScrollAnimation();
        });
    });
    
    simulatePriceUpdates();

    // Navbar scroll effect
    let lastScroll = 0;
    window.addEventListener('scroll', () => {
        const nav = document.getElementById('main-nav');
        const currentScroll = window.pageYOffset;
        
        if (currentScroll > 100) {
            nav.style.background = 'rgba(255, 255, 255, 0.92)';
            nav.style.backdropFilter = 'blur(20px)';
            nav.style.borderBottomColor = 'rgba(0, 0, 0, 0.06)';
            nav.querySelectorAll('.nav-link:not(.btn-nav)').forEach(l => l.style.color = '#555');
            nav.querySelector('.logo-text').style.color = '#1a1a2a';
        } else {
            nav.style.background = 'rgba(0, 0, 0, 0.4)';
            nav.style.backdropFilter = 'blur(20px)';
            nav.style.borderBottomColor = 'rgba(255, 255, 255, 0.06)';
            nav.querySelectorAll('.nav-link:not(.btn-nav)').forEach(l => l.style.color = '');
            nav.querySelector('.logo-text').style.color = '';
        }
        
        lastScroll = currentScroll;
    });
});
