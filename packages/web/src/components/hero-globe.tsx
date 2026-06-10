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

    // Camera — positioned to show globe offset to the right
    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(-1.5, 0.8, 3.5); // offset left and slightly above to show North America prominently
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); // cap at 2x for performance
    container.appendChild(renderer.domElement);

    // ── Globe sphere — dark with subtle edge glow ──
    const globeRadius = 1.5;
    const globeGeometry = new THREE.SphereGeometry(globeRadius, 64, 64);

    // Custom shader material for the globe
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
          // Fresnel-style edge glow — brighter at the edges, dark in the center
          float intensity = pow(0.65 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.5);
          // Dark base color with subtle blue edge glow
          vec3 baseColor = vec3(0.04, 0.05, 0.08); // very dark navy
          vec3 glowColor = vec3(0.15, 0.25, 0.45); // subtle blue
          vec3 color = mix(baseColor, glowColor, intensity);
          gl_FragColor = vec4(color, 1.0);
        }
      `,
      side: THREE.FrontSide,
    });

    const globe = new THREE.Mesh(globeGeometry, globeMaterial);
    scene.add(globe);

    // ── Latitude lines (every 30 degrees = 6 lines) ──
    const latitudes = [-60, -30, 0, 30, 60];
    latitudes.forEach((lat) => {
      const phi = (90 - lat) * (Math.PI / 180);
      const radius = globeRadius * Math.sin(phi) * 1.002; // slightly above surface
      const y = globeRadius * Math.cos(phi) * 1.002;
      const circleGeometry = new THREE.RingGeometry(radius - 0.001, radius + 0.001, 128);
      const circleMaterial = new THREE.MeshBasicMaterial({
        color: 0x3f3f46, // zinc-700
        transparent: true,
        opacity: 0.12,
        side: THREE.DoubleSide,
      });
      const circle = new THREE.Mesh(circleGeometry, circleMaterial);
      circle.position.y = y;
      circle.rotation.x = Math.PI / 2;
      globe.add(circle);
    });

    // ── Longitude lines (every 30 degrees = 12 lines) ──
    for (let i = 0; i < 12; i++) {
      const curve = new THREE.EllipseCurve(0, 0, globeRadius * 1.002, globeRadius * 1.002, 0, 2 * Math.PI, false, 0);
      const points = curve.getPoints(128);
      const geometry = new THREE.BufferGeometry().setFromPoints(
        points.map((p) => new THREE.Vector3(p.x, p.y, 0)),
      );
      const material = new THREE.LineBasicMaterial({
        color: 0x3f3f46,
        transparent: true,
        opacity: 0.08,
      });
      const line = new THREE.Line(geometry, material);
      line.rotation.y = i * 30 * (Math.PI / 180);
      globe.add(line);
    }

    // ── Glowing data points — US city coordinates [latitude, longitude] ──
    const cities = [
      { name: "NYC", lat: 40.71, lng: -74.01 },
      { name: "LA", lat: 34.05, lng: -118.24 },
      { name: "Houston", lat: 29.76, lng: -95.37 },
      { name: "Chicago", lat: 41.88, lng: -87.63 },
      { name: "Phoenix", lat: 33.45, lng: -112.07 },
      { name: "Denver", lat: 39.74, lng: -104.99 },
      { name: "Atlanta", lat: 33.75, lng: -84.39 },
      { name: "Seattle", lat: 47.61, lng: -122.33 },
      { name: "Dallas", lat: 32.78, lng: -96.8 },
      { name: "Miami", lat: 25.76, lng: -80.19 },
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

    // Create dot meshes
    const dots: THREE.Mesh[] = [];
    const dotGeometry = new THREE.SphereGeometry(0.02, 16, 16); // small sphere

    cities.forEach((city, i) => {
      // Inner bright dot
      const dotMaterial = new THREE.MeshBasicMaterial({
        color: 0xf59e0b, // amber-500
        transparent: true,
        opacity: 0.9,
      });
      const dot = new THREE.Mesh(dotGeometry, dotMaterial);
      const pos = latLngToVector3(city.lat, city.lng, globeRadius * 1.01);
      dot.position.copy(pos);
      globe.add(dot);
      dots.push(dot);

      // Outer glow (larger, more transparent)
      const glowGeometry = new THREE.SphereGeometry(0.05, 16, 16);
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: 0xf59e0b,
        transparent: true,
        opacity: 0.25,
      });
      const glow = new THREE.Mesh(glowGeometry, glowMaterial);
      glow.position.copy(pos);
      globe.add(glow);

      // Store reference for animation
      (dot as unknown as { _glowMesh: THREE.Mesh })._glowMesh = glow;
      (dot as unknown as { _phaseOffset: number })._phaseOffset = i * 0.7; // stagger the pulse timing
    });

    // ── Atmosphere halo — a slightly larger transparent sphere with reverse fresnel ──
    const atmosphereGeometry = new THREE.SphereGeometry(globeRadius * 1.15, 64, 64);
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
          float intensity = pow(0.6 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.0);
          vec3 color = vec3(0.12, 0.20, 0.40); // dark blue atmosphere
          gl_FragColor = vec4(color, intensity * 0.4);
        }
      `,
      side: THREE.BackSide,
      transparent: true,
      blending: THREE.AdditiveBlending,
    });
    const atmosphere = new THREE.Mesh(atmosphereGeometry, atmosphereMaterial);
    scene.add(atmosphere);

    // ── Lighting ──
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
        globe.rotation.y = elapsed * ((2 * Math.PI) / 90); // 90-second full rotation
      }

      // Pulse the data point dots
      dots.forEach((dot) => {
        const phase = (dot as unknown as { _phaseOffset: number })._phaseOffset;
        const glowMesh = (dot as unknown as { _glowMesh: THREE.Mesh })._glowMesh;

        // Pulse opacity between 0.5 and 1.0 over a 3-second cycle
        const pulse = 0.75 + 0.25 * Math.sin(elapsed * 2.1 + phase);
        (dot.material as THREE.MeshBasicMaterial).opacity = pulse;

        // Pulse the glow between 0.1 and 0.35
        const glowPulse = 0.2 + 0.15 * Math.sin(elapsed * 2.1 + phase);
        (glowMesh.material as THREE.MeshBasicMaterial).opacity = glowPulse;

        // Slight scale pulse on the glow
        const scalePulse = 1.0 + 0.3 * Math.sin(elapsed * 2.1 + phase);
        glowMesh.scale.setScalar(scalePulse);
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
      // dispose all geometries, materials, textures
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else {
            obj.material.dispose();
          }
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
