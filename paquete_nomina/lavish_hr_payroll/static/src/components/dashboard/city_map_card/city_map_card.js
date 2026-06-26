/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";

export class CityMapCard extends Component {
    static template = "lavish_hr_payroll.CityMapCard";
    static props = {
        cityData: Object,
        period: Object,
    };

    setup() {
        this.mapRef = useRef("mapContainer");
        this.map = null;
        this.markers = [];

        onMounted(() => {
            this.loadLeaflet();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
            }
        });
    }

    async loadLeaflet() {
        if (!window.L) {
            // Cargar CSS de Leaflet
            const cssLink = document.createElement('link');
            cssLink.rel = 'stylesheet';
            cssLink.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(cssLink);

            // Cargar JS de Leaflet
            await new Promise((resolve) => {
                const script = document.createElement('script');
                script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
                script.onload = resolve;
                document.head.appendChild(script);
            });
        }

        // Esperar a que el contenedor esté listo
        setTimeout(() => this.initMap(), 100);
    }

    initMap() {
        const container = this.mapRef.el;
        if (!container || !window.L || this.map) return;

        // Centro de Colombia
        const colombiaCenter = [4.5709, -74.2973];

        this.map = L.map(container, {
            zoomControl: false,
            attributionControl: false,
            dragging: true,
            scrollWheelZoom: false,
        }).setView(colombiaCenter, 5);

        // Tiles de OpenStreetMap con estilo claro
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
        }).addTo(this.map);

        // Agregar marcadores de ciudades
        this.addCityMarkers();

        // Control de zoom pequeño
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
    }

    addCityMarkers() {
        if (!this.map || !this.hasData) return;

        const maxCount = this.maxCount;

        this.pinnedCities.forEach((city, index) => {
            const coords = this.cityCoordinates[city.key];
            if (!coords) return;

            const size = this.getMarkerSize(city.count, maxCount);
            const isTop3 = index < 3;

            // Crear icono personalizado
            const icon = L.divIcon({
                className: 'city-marker-icon',
                html: `
                    <div class="city-marker ${isTop3 ? 'is-top' : ''}" style="--size: ${size}px;">
                        <span class="city-marker-dot"></span>
                        <span class="city-marker-label">${city.name}</span>
                    </div>
                `,
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2],
            });

            const marker = L.marker([coords.lat, coords.lng], { icon })
                .bindPopup(`<strong>${city.name}</strong><br>${city.count} empleados (${city.percent}%)`)
                .addTo(this.map);

            this.markers.push(marker);
        });

        // Ajustar vista a los marcadores si hay datos
        if (this.markers.length > 0) {
            const group = L.featureGroup(this.markers);
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    }

    getMarkerSize(count, maxCount) {
        const ratio = count / maxCount;
        return Math.round(14 + ratio * 16);
    }

    get cities() {
        return this.props.cityData?.cities || [];
    }

    get totalEmployees() {
        return this.props.cityData?.total || 0;
    }

    get hasData() {
        return this.cities.length > 0;
    }

    get cityItems() {
        // Agrupar ciudades con el mismo key normalizado (alias) para evitar duplicados
        const merged = new Map();
        this.cities.forEach((city) => {
            const key = this.normalizeCityKey(city.name);
            const normalizedKey = this.cityAliases[key] || key;
            if (merged.has(normalizedKey)) {
                merged.get(normalizedKey).count += (city.count || 0);
            } else {
                merged.set(normalizedKey, {
                    ...city,
                    key: normalizedKey,
                    coords: this.cityCoordinates[normalizedKey] || null,
                });
            }
        });
        return Array.from(merged.values())
            .sort((a, b) => (b.count || 0) - (a.count || 0))
            .map((city, index) => ({
                ...city,
                rank: index + 1,
                percent: this.totalEmployees > 0
                    ? ((city.count / this.totalEmployees) * 100).toFixed(1)
                    : "0.0",
            }));
    }

    get pinnedCities() {
        return this.cityItems.filter((city) => city.coords);
    }

    get otherCities() {
        return this.cityItems.filter((city) => !city.coords);
    }

    get topCities() {
        return this.cityItems.slice(0, 8);
    }

    get maxCount() {
        return this.cities.reduce((max, city) => Math.max(max, city.count || 0), 1);
    }

    normalizeCityKey(name) {
        return (name || "")
            .toString()
            .trim()
            .toUpperCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036F]/g, "");
    }

    get cityAliases() {
        return {
            "BOGOTA D.C": "BOGOTA",
            "BOGOTA DC": "BOGOTA",
            "SANTA FE DE BOGOTA": "BOGOTA",
        };
    }

    // Coordenadas reales de ciudades colombianas
    get cityCoordinates() {
        return {
            "BOGOTA": { lat: 4.7110, lng: -74.0721 },
            "MEDELLIN": { lat: 6.2442, lng: -75.5812 },
            "ENVIGADO": { lat: 6.1691, lng: -75.5860 },
            "BELLO": { lat: 6.3378, lng: -75.5585 },
            "ITAGUI": { lat: 6.1846, lng: -75.5993 },
            "SABANETA": { lat: 6.1517, lng: -75.6163 },
            "CALI": { lat: 3.4516, lng: -76.5320 },
            "BARRANQUILLA": { lat: 10.9685, lng: -74.7813 },
            "CARTAGENA": { lat: 10.3910, lng: -75.4794 },
            "SANTA MARTA": { lat: 11.2408, lng: -74.1990 },
            "BUCARAMANGA": { lat: 7.1254, lng: -73.1198 },
            "CUCUTA": { lat: 7.8939, lng: -72.5078 },
            "VILLAVICENCIO": { lat: 4.1420, lng: -73.6266 },
            "PEREIRA": { lat: 4.8133, lng: -75.6961 },
            "MANIZALES": { lat: 5.0689, lng: -75.5174 },
            "ARMENIA": { lat: 4.5339, lng: -75.6811 },
            "IBAGUE": { lat: 4.4389, lng: -75.2322 },
            "NEIVA": { lat: 2.9273, lng: -75.2819 },
            "PASTO": { lat: 1.2136, lng: -77.2811 },
            "MONTERIA": { lat: 8.7479, lng: -75.8814 },
            "VALLEDUPAR": { lat: 10.4631, lng: -73.2532 },
            "QUIBDO": { lat: 5.6947, lng: -76.6611 },
            "TUNJA": { lat: 5.5353, lng: -73.3678 },
            "POPAYAN": { lat: 2.4419, lng: -76.6061 },
            "FLORENCIA": { lat: 1.6144, lng: -75.6062 },
            "RIOHACHA": { lat: 11.5444, lng: -72.9072 },
            "SINCELEJO": { lat: 9.3047, lng: -75.3978 },
            "YOPAL": { lat: 5.3378, lng: -72.3959 },
            "LETICIA": { lat: -4.2153, lng: -69.9406 },
            "APARTADO": { lat: 7.8833, lng: -76.6333 },
            "TURBO": { lat: 8.0931, lng: -76.7281 },
            "RIONEGRO": { lat: 6.1552, lng: -75.3743 },
            "SOACHA": { lat: 4.5794, lng: -74.2169 },
            "CHIA": { lat: 4.8637, lng: -74.0540 },
            "ZIPAQUIRA": { lat: 5.0224, lng: -74.0059 },
            "PALMIRA": { lat: 3.5395, lng: -76.3036 },
            "BUENAVENTURA": { lat: 3.8801, lng: -77.0311 },
            "TULUA": { lat: 4.0848, lng: -76.1996 },
            "CARTAGO": { lat: 4.7461, lng: -75.9117 },
            "SOLEDAD": { lat: 10.9180, lng: -74.7645 },
            "MAICAO": { lat: 11.3833, lng: -72.2500 },
            "DOSQUEBRADAS": { lat: 4.8397, lng: -75.6721 },
            "BARRANCABERMEJA": { lat: 7.0647, lng: -73.8547 },
            "SOGAMOSO": { lat: 5.7142, lng: -72.9342 },
            "DUITAMA": { lat: 5.8269, lng: -73.0333 },
            "GIRARDOT": { lat: 4.3028, lng: -74.8039 },
            "FUSAGASUGA": { lat: 4.3378, lng: -74.3639 },
            "FACATATIVA": { lat: 4.8150, lng: -74.3547 },
            "PIEDECUESTA": { lat: 6.9875, lng: -73.0500 },
            "FLORIDABLANCA": { lat: 7.0628, lng: -73.0875 },
            "GIRON": { lat: 7.0683, lng: -73.1711 },
        };
    }
}
