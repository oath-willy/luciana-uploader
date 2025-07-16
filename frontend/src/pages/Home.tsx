import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div style={{ padding: '2rem' }}>
      <h1>Luciana Project</h1>
      <ul>
        <li><Link to="/explorer">🔍 Esplora risorse (bronze)</Link></li>
      </ul>
    </div>
  );
}
