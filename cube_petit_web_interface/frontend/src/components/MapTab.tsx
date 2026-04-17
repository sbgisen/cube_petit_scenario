import { useEffect, useState } from 'react';

interface Place {
  category: string;
  name: string;
  pose: number[];
}

interface Props {
  namespace: string;
  apiUrl: string;
}

const CATEGORIES = ['patrol', 'favorite', 'dock'];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: 'var(--t-text-muted)', fontSize: 14, fontWeight: 'bold', marginBottom: 8 }}>
      {children}
    </div>
  );
}

export function MapTab({ namespace, apiUrl }: Props) {
  const [maps, setMaps] = useState<string[]>([]);
  const [selectedMap, setSelectedMap] = useState('');
  const [loadMsg, setLoadMsg] = useState('');
  const [places, setPlaces] = useState<Place[]>([]);
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState('patrol');
  const [addMsg, setAddMsg] = useState('');

  const fetchPlaces = () => {
    fetch(`${apiUrl}/places`)
      .then(r => r.json())
      .then(d => setPlaces(d.places ?? []))
      .catch(() => {});
  };

  useEffect(() => {
    fetch(`${apiUrl}/map/list`)
      .then(r => r.json())
      .then(d => { setMaps(d.maps ?? []); if (d.maps?.length) setSelectedMap(d.maps[0]); })
      .catch(() => {});
    fetchPlaces();
  }, [apiUrl]);

  const loadMap = () => {
    setLoadMsg('読み込み中...');
    fetch(`${apiUrl}/map/load?namespace=${namespace}&map_name=${selectedMap}`, { method: 'POST' })
      .then(r => r.json())
      .then(d => setLoadMsg(d.ok ? '読み込み完了' : `失敗: ${d.error ?? ''}`))
      .catch(() => setLoadMsg('エラー'));
  };

  const addPlace = () => {
    if (!newName.trim()) return;
    setAddMsg('保存中...');
    fetch(`${apiUrl}/places/add?namespace=${namespace}&name=${encodeURIComponent(newName.trim())}&category=${newCategory}`, { method: 'POST' })
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          setAddMsg(`保存完了 (${d.pose?.map((v: number) => v.toFixed(2)).join(', ')})`);
          setNewName('');
          fetchPlaces();
        } else {
          setAddMsg(`失敗: ${d.error ?? ''}`);
        }
      })
      .catch(() => setAddMsg('エラー'));
  };

  const removePlace = (category: string, name: string) => {
    fetch(`${apiUrl}/places/remove?category=${category}&name=${encodeURIComponent(name)}`, { method: 'DELETE' })
      .then(() => fetchPlaces())
      .catch(() => {});
  };

  const byCategory = CATEGORIES.reduce((acc, cat) => {
    acc[cat] = places.filter(p => p.category === cat);
    return acc;
  }, {} as Record<string, Place[]>);

  return (
    <div style={{ display: 'flex', gap: 24, padding: 8, flexWrap: 'wrap', alignContent: 'flex-start', overflowY: 'auto', height: '100%' }}>

      {/* マップ選択 */}
      <div style={{ minWidth: 240 }}>
        <SectionTitle>マップ選択</SectionTitle>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
          <select
            value={selectedMap}
            onChange={e => setSelectedMap(e.target.value)}
            style={{
              flex: 1, padding: '6px 10px', borderRadius: 8,
              border: '1px solid var(--t-border2)',
              background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
            }}
          >
            {maps.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <button
            onClick={loadMap}
            style={{
              padding: '6px 14px', borderRadius: 12, border: 'none', cursor: 'pointer',
              background: '#ff6600', color: '#fff', fontSize: 13,
            }}
          >読み込み</button>
        </div>
        {loadMsg && <div style={{ fontSize: 12, color: 'var(--t-text-muted)' }}>{loadMsg}</div>}
      </div>

      {/* ポイント追加 */}
      <div style={{ minWidth: 260 }}>
        <SectionTitle>現在地を保存</SectionTitle>
        <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
          <input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addPlace()}
            placeholder="名前 (例: sofa)"
            style={{
              flex: 1, padding: '6px 10px', borderRadius: 8,
              border: '1px solid var(--t-border2)',
              background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
            }}
          />
          <select
            value={newCategory}
            onChange={e => setNewCategory(e.target.value)}
            style={{
              padding: '6px 8px', borderRadius: 8,
              border: '1px solid var(--t-border2)',
              background: 'var(--t-surface)', color: 'var(--t-text)', fontSize: 13,
            }}
          >
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <button
          onClick={addPlace}
          disabled={!newName.trim()}
          style={{
            width: '100%', padding: '8px 0', borderRadius: 10, border: 'none',
            cursor: newName.trim() ? 'pointer' : 'not-allowed',
            background: newName.trim() ? '#ff6600' : 'var(--t-border2)',
            color: 'var(--t-text)', fontSize: 13,
          }}
        >現在地を保存</button>
        {addMsg && <div style={{ fontSize: 12, color: 'var(--t-text-muted)', marginTop: 4 }}>{addMsg}</div>}
      </div>

      {/* ポイント一覧 */}
      <div style={{ minWidth: 280, flex: 1 }}>
        <SectionTitle>ポイント一覧</SectionTitle>
        {CATEGORIES.map(cat => {
          const list = byCategory[cat];
          if (!list?.length) return null;
          return (
            <div key={cat} style={{ marginBottom: 12 }}>
              <div style={{ color: 'var(--t-text-muted)', fontSize: 11, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>
                {cat}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {list.map(p => (
                  <div key={p.name} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '5px 10px', borderRadius: 8, background: 'var(--t-overlay)',
                  }}>
                    <span style={{ color: 'var(--t-text)', fontSize: 13, flex: 1 }}>{p.name}</span>
                    <span style={{ color: 'var(--t-text-muted)', fontSize: 11 }}>
                      {p.pose.map(v => v.toFixed(2)).join(', ')}
                    </span>
                    <button
                      onClick={() => removePlace(p.category, p.name)}
                      style={{
                        padding: '2px 6px', borderRadius: 6, border: 'none',
                        cursor: 'pointer', background: '#442222', color: '#ff6666', fontSize: 11,
                      }}
                    >✕</button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {places.length === 0 && (
          <div style={{ color: 'var(--t-text-muted)', fontSize: 13 }}>ポイントなし</div>
        )}
      </div>

    </div>
  );
}
