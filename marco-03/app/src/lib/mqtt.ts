/**
 * Uma única conexão MQTT para o app inteiro, sobre WebSocket seguro.
 *
 * Usa o paho-mqtt, que é JavaScript puro em cima do WebSocket do React Native:
 * roda no Expo Go sem módulo nativo. Reconecta sozinho e refaz as assinaturas.
 */
import Paho from 'paho-mqtt';
import { BROKER_URL, MQTT_SENHA, MQTT_USUARIO } from './config';

type Ouvinte = (topico: string, texto: string) => void;
type OuvinteConexao = (conectado: boolean) => void;

const ESPERA_RECONEXAO_MS = 3000;

class Conexao {
  private cliente: Paho.Client | null = null;
  private assinaturas = new Map<string, Set<Ouvinte>>();
  private ouvintesConexao = new Set<OuvinteConexao>();
  private tentando = false;
  conectado = false;

  private iniciar() {
    if (this.cliente || this.tentando) return;
    this.tentando = true;
    const id = 'presenca-app-' + Math.random().toString(16).slice(2, 10);
    const c = new Paho.Client(BROKER_URL, id);
    c.onConnectionLost = () => {
      this.mudar(false);
      this.cliente = null;
      setTimeout(() => this.iniciar(), ESPERA_RECONEXAO_MS);
    };
    c.onMessageArrived = (m: Paho.Message) => {
      for (const [filtro, ouvintes] of this.assinaturas) {
        if (casa(filtro, m.destinationName)) ouvintes.forEach((o) => o(m.destinationName, m.payloadString));
      }
    };
    c.connect({
      useSSL: true,                 // TLS: o HiveMQ Cloud não aceita conexão aberta
      userName: MQTT_USUARIO,       // autenticação MQTT do papel "app"
      password: MQTT_SENHA,
      keepAliveInterval: 30,
      cleanSession: true,
      timeout: 10,
      onSuccess: () => {
        this.tentando = false;
        this.cliente = c;
        for (const t of this.assinaturas.keys()) c.subscribe(t, { qos: 1 });
        this.mudar(true);
      },
      onFailure: () => {
        this.tentando = false;
        setTimeout(() => this.iniciar(), ESPERA_RECONEXAO_MS);
      },
    });
  }

  private mudar(v: boolean) {
    this.conectado = v;
    this.ouvintesConexao.forEach((o) => o(v));
  }

  aoMudarConexao(o: OuvinteConexao) {
    this.iniciar();
    this.ouvintesConexao.add(o);
    o(this.conectado);
    return () => { this.ouvintesConexao.delete(o); };
  }

  assinar(topico: string, o: Ouvinte) {
    this.iniciar();
    let s = this.assinaturas.get(topico);
    if (!s) {
      s = new Set();
      this.assinaturas.set(topico, s);
      if (this.conectado) this.cliente?.subscribe(topico, { qos: 1 });
    }
    s.add(o);
    return () => {
      s!.delete(o);
      if (s!.size === 0) {
        this.assinaturas.delete(topico);
        if (this.conectado) this.cliente?.unsubscribe(topico);
      }
    };
  }

  /** Devolve false se não há conexão agora (quem chamou decide se retém). */
  publicar(topico: string, texto: string, opcoes: { retido?: boolean; qos?: 0 | 1 } = {}) {
    if (!this.conectado || !this.cliente) return false;
    try {
      const m = new Paho.Message(texto);
      m.destinationName = topico;
      m.qos = opcoes.qos ?? 0;
      m.retained = opcoes.retido ?? false;
      this.cliente.send(m);
      return true;
    } catch {
      return false;
    }
  }
}

/** Filtro MQTT com + e #. */
function casa(filtro: string, topico: string) {
  const f = filtro.split('/');
  const t = topico.split('/');
  for (let i = 0; i < f.length; i++) {
    if (f[i] === '#') return true;
    if (f[i] !== '+' && f[i] !== t[i]) return false;
  }
  return f.length === t.length;
}

export const mqtt = new Conexao();
