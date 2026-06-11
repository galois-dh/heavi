"use client";
import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function HeroGlobe() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;

    // Check for WebGL support
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (!gl) return; // Fallback: just show dark background

    // Check for reduced motion preference
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x09090b); // zinc-950

    // Camera — positioned to show globe offset to the right. The globe is larger
    // (radius 1.8) so the camera sits a little farther back and to the left.
    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(-1.4, 0.7, 3.7);
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // cap at 2x for performance
    container.appendChild(renderer.domElement);

    // ── Globe sphere — dark surface with a bright blue-white Fresnel rim ──
    const globeRadius = 1.8; // +20% over the original 1.5
    const globeGeometry = new THREE.SphereGeometry(globeRadius, 64, 64);

    const globeMaterial = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vPosition = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          // facing = 1 toward the camera, 0 at the silhouette edge.
          float facing = max(dot(vNormal, vec3(0.0, 0.0, 1.0)), 0.0);
          float fresnel = pow(1.0 - facing, 2.2);
          // Dark navy base (#0a1020), lifted slightly on the lit face so the
          // whole sphere reads, not just the rim.
          vec3 baseColor = vec3(0.039, 0.063, 0.125);
          vec3 surface = baseColor + vec3(0.025, 0.035, 0.060) * facing;
          // Bright blue-white rim glow, added so the edge clearly pops.
          vec3 rimColor = vec3(0.45, 0.65, 1.0);
          vec3 color = surface + rimColor * fresnel * 1.35;
          gl_FragColor = vec4(color, 1.0);
        }
      `,
      side: THREE.FrontSide,
    });

    const globe = new THREE.Mesh(globeGeometry, globeMaterial);
    scene.add(globe);

    // ── Latitude lines (every 30 degrees) — brighter, slightly thicker ──
    const latitudes = [-60, -30, 0, 30, 60];
    latitudes.forEach((lat) => {
      const phi = (90 - lat) * (Math.PI / 180);
      const radius = globeRadius * Math.sin(phi) * 1.002; // slightly above surface
      const y = globeRadius * Math.cos(phi) * 1.002;
      const circleGeometry = new THREE.RingGeometry(radius - 0.0025, radius + 0.0025, 128);
      const circleMaterial = new THREE.MeshBasicMaterial({
        color: 0x52525b, // zinc-600
        transparent: true,
        opacity: 0.25,
        side: THREE.DoubleSide,
      });
      const circle = new THREE.Mesh(circleGeometry, circleMaterial);
      circle.position.y = y;
      circle.rotation.x = Math.PI / 2;
      globe.add(circle);
    });

    // ── Longitude lines (meridians every 30 degrees) — brighter, thicker ──
    // Great-circle rings in the XY plane (through the poles), rotated about Y.
    const lonRingGeometry = new THREE.RingGeometry(globeRadius - 0.0025, globeRadius + 0.0025, 256);
    for (let i = 0; i < 6; i++) {
      const material = new THREE.MeshBasicMaterial({
        color: 0x52525b,
        transparent: true,
        opacity: 0.18,
        side: THREE.DoubleSide,
      });
      const ring = new THREE.Mesh(lonRingGeometry, material);
      ring.rotation.y = i * 30 * (Math.PI / 180);
      globe.add(ring);
    }

    // ── Data points — 39 cities across every continent ──
    const cities = [
      { name: "New York", lat: 40.71, lng: -74.01 },
      { name: "Los Angeles", lat: 34.05, lng: -118.24 },
      { name: "Chicago", lat: 41.88, lng: -87.63 },
      { name: "Houston", lat: 29.76, lng: -95.37 },
      { name: "Toronto", lat: 43.65, lng: -79.38 },
      { name: "Mexico City", lat: 19.43, lng: -99.13 },
      { name: "San Francisco", lat: 37.77, lng: -122.42 },
      { name: "Miami", lat: 25.76, lng: -80.19 },
      { name: "São Paulo", lat: -23.55, lng: -46.63 },
      { name: "Buenos Aires", lat: -34.6, lng: -58.38 },
      { name: "Lima", lat: -12.05, lng: -77.04 },
      { name: "Bogotá", lat: 4.71, lng: -74.07 },
      { name: "Santiago", lat: -33.45, lng: -70.67 },
      { name: "Rio de Janeiro", lat: -22.91, lng: -43.17 },
      { name: "London", lat: 51.51, lng: -0.13 },
      { name: "Paris", lat: 48.86, lng: 2.35 },
      { name: "Berlin", lat: 52.52, lng: 13.4 },
      { name: "Madrid", lat: 40.42, lng: -3.7 },
      { name: "Rome", lat: 41.9, lng: 12.5 },
      { name: "Moscow", lat: 55.76, lng: 37.62 },
      { name: "Istanbul", lat: 41.01, lng: 28.98 },
      { name: "Stockholm", lat: 59.33, lng: 18.07 },
      { name: "Cairo", lat: 30.04, lng: 31.24 },
      { name: "Lagos", lat: 6.52, lng: 3.38 },
      { name: "Nairobi", lat: -1.29, lng: 36.82 },
      { name: "Johannesburg", lat: -26.2, lng: 28.05 },
      { name: "Casablanca", lat: 33.57, lng: -7.59 },
      { name: "Tokyo", lat: 35.68, lng: 139.69 },
      { name: "Beijing", lat: 39.9, lng: 116.41 },
      { name: "Shanghai", lat: 31.23, lng: 121.47 },
      { name: "Mumbai", lat: 19.08, lng: 72.88 },
      { name: "Delhi", lat: 28.61, lng: 77.21 },
      { name: "Singapore", lat: 1.35, lng: 103.82 },
      { name: "Dubai", lat: 25.2, lng: 55.27 },
      { name: "Seoul", lat: 37.57, lng: 126.98 },
      { name: "Bangkok", lat: 13.76, lng: 100.5 },
      { name: "Hong Kong", lat: 22.32, lng: 114.17 },
      { name: "Sydney", lat: -33.87, lng: 151.21 },
      { name: "Auckland", lat: -36.85, lng: 174.76 },
    ];

    // Convert lat/lng to 3D position on sphere surface
    function latLngToVector3(lat: number, lng: number, radius: number): THREE.Vector3 {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      const x = -radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.cos(phi);
      const z = radius * Math.sin(phi) * Math.sin(theta);
      return new THREE.Vector3(x, y, z);
    }

    // Shared geometries (created once) — larger inner dot + outer glow.
    const dotGeometry = new THREE.SphereGeometry(0.03, 16, 16);
    const glowGeometry = new THREE.SphereGeometry(0.07, 16, 16);

    const dots: THREE.Mesh[] = [];
    const dotPositions: THREE.Vector3[] = [];

    cities.forEach((city, i) => {
      const pos = latLngToVector3(city.lat, city.lng, globeRadius * 1.01);
      dotPositions.push(pos);

      // Inner bright dot
      const dotMaterial = new THREE.MeshBasicMaterial({
        color: 0xf59e0b, // amber-500
        transparent: true,
        opacity: 0.95,
      });
      const dot = new THREE.Mesh(dotGeometry, dotMaterial);
      dot.position.copy(pos);
      globe.add(dot);
      dots.push(dot);

      // Outer glow (larger, more transparent)
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: 0xf59e0b,
        transparent: true,
        opacity: 0.4,
      });
      const glow = new THREE.Mesh(glowGeometry, glowMaterial);
      glow.position.copy(pos);
      globe.add(glow);

      (dot as unknown as { _glowMesh: THREE.Mesh })._glowMesh = glow;
      (dot as unknown as { _phaseOffset: number })._phaseOffset = i * 0.7;
    });

    // ── Connection arcs — flight-path style curves between some cities ──
    const arcPairs: [number, number][] = [
      [0, 14], // New York → London
      [1, 27], // Los Angeles → Tokyo
      [14, 33], // London → Dubai
      [33, 32], // Dubai → Singapore
      [8, 23], // São Paulo → Lagos
      [37, 32], // Sydney → Singapore
      [19, 28], // Moscow → Beijing
      [6, 37], // San Francisco → Sydney
    ];
    const arcs: THREE.Line[] = [];
    arcPairs.forEach(([a, b], i) => {
      const start = dotPositions[a];
      const end = dotPositions[b];
      // Control point bowed outward from the surface; longer hops bow higher.
      const ratio = start.distanceTo(end) / (2 * globeRadius);
      const lift = globeRadius * (1.15 + 0.3 * ratio);
      const control = start.clone().add(end).multiplyScalar(0.5).normalize().multiplyScalar(lift);
      const curve = new THREE.QuadraticBezierCurve3(start.clone(), control, end.clone());
      const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(64));
      const material = new THREE.LineBasicMaterial({
        color: 0xf59e0b, // amber
        transparent: true,
        opacity: 0.15,
      });
      const line = new THREE.Line(geometry, material);
      (line as unknown as { _phaseOffset: number })._phaseOffset = i * 0.9;
      globe.add(line);
      arcs.push(line);
    });

    // ── Atmosphere halo — larger, brighter reverse-Fresnel glow ──
    const atmosphereGeometry = new THREE.SphereGeometry(globeRadius * 1.25, 64, 64);
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
          float d = dot(vNormal, vec3(0.0, 0.0, 1.0));
          float intensity = pow(max(0.85 - d, 0.0), 2.0);
          vec3 color = vec3(0.25, 0.45, 0.95); // blue-white atmosphere
          gl_FragColor = vec4(color, intensity * 0.75);
        }
      `,
      side: THREE.BackSide,
      transparent: true,
      blending: THREE.AdditiveBlending,
    });
    const atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphere);

    // ── Lighting (ambient only; the materials are unlit/shader-based) ──
    const ambientLight = new THREE.AmbientLight(0x222244, 0.5);
    scene.add(ambientLight);

    // ── Animation loop ──
    const clock = new THREE.Clock();
    let rafId = 0;

    function animate() {
      rafId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      // Slow rotation (one full rotation every 90 seconds)
      if (!prefersReducedMotion) {
        globe.rotation.y = elapsed * ((2 * Math.PI) / 90);
      }

      // Pulse the data point dots
      dots.forEach((dot) => {
        const phase = (dot as unknown as { _phaseOffset: number })._phaseOffset;
        const glowMesh = (dot as unknown as { _glowMesh: THREE.Mesh })._glowMesh;

        // Inner dot opacity 0.55 → 0.95
        (dot.material as THREE.MeshBasicMaterial).opacity = 0.75 + 0.2 * Math.sin(elapsed * 2.1 + phase);

        // Glow opacity 0.16 → 0.40 with a slight scale pulse
        (glowMesh.material as THREE.MeshBasicMaterial).opacity = 0.28 + 0.12 * Math.sin(elapsed * 2.1 + phase);
        glowMesh.scale.setScalar(1.0 + 0.3 * Math.sin(elapsed * 2.1 + phase));
      });

      // Slowly pulse the connection arcs (opacity ~0.06 → 0.20)
      arcs.forEach((arc) => {
        const phase = (arc as unknown as { _phaseOffset: number })._phaseOffset;
        (arc.material as THREE.LineBasicMaterial).opacity = 0.13 + 0.07 * Math.sin(elapsed * 0.6 + phase);
      });

      renderer.render(scene, camera);
    }

    animate();

    // ── Resize handler ──
    function handleResize() {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }
    window.addEventListener("resize", handleResize);

    // Cleanup
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      // dispose all geometries + materials (meshes and lines)
      scene.traverse((obj) => {
        const node = obj as THREE.Mesh | THREE.Line;
        if (node.geometry) node.geometry.dispose();
        const material = node.material;
        if (material) {
          if (Array.isArray(material)) material.forEach((m) => m.dispose());
          else material.dispose();
        }
      });
      container.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 pointer-events-none"
      aria-hidden="true"
    />
  );
}
