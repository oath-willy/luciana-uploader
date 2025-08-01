import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div style={{ padding: '2rem' }}>
      <h1>LUCIANA PROJECT</h1>
      <h2>TEST PAGE</h2>
      <ul>
        <li><Link to="/storage-browser">BRONZE STORAGE BROWSER</Link></li>
        <li><Link to="/navigator">Luciana Navigator</Link></li>
      </ul>
    </div>
  );
}
