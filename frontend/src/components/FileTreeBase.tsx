import { useEffect, useState } from 'react';
import type { JSX } from 'react';

export type FileNode = {
  name: string;
  type: 'folder' | 'file';
  children?: FileNode[];
};

type InternalNode = {
  name: string;
  type: 'folder' | 'file';
  children?: { [key: string]: InternalNode };
};

function buildTree(paths: string[]): FileNode[] {
  const root: { [key: string]: InternalNode } = {};

  for (const path of paths) {
    const parts = path.split('/');
    let current = root;

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1 && !path.endsWith('/');
      const key = part + (isFile ? '' : '/');

      if (!current[key]) {
        current[key] = {
          name: part,
          type: isFile ? 'file' : 'folder',
          ...(isFile ? {} : { children: {} }),
        };
      }

      if (!isFile) {
        current = current[key].children!;
      }
    });
  }

  function convert(node: { [key: string]: InternalNode }): FileNode[] {
    return Object.values(node).map((entry) => ({
      name: entry.name,
      type: entry.type,
      children: entry.children ? convert(entry.children) : undefined,
    }));
  }

  return convert(root);
}

interface FileTreeBaseProps {
  files: string[];
  autoExpandPath?: string;
  render?: (node: FileNode, depth: number, path: string) => JSX.Element;
}

export default function FileTreeBase({ files, autoExpandPath, render }: FileTreeBaseProps) {
  const [tree, setTree] = useState<FileNode[]>([]);

  useEffect(() => {
    const structured = buildTree(files);
    setTree(structured);
  }, [files]);

  const renderNode = (node: FileNode, depth: number, parentPath: string): JSX.Element => {
    const currentPath = parentPath ? `${parentPath}/${node.name}` : node.name;
    const expanded = autoExpandPath?.startsWith(currentPath);
    return (
      <div key={currentPath} style={{ paddingLeft: depth * 20 }}>
        {node.type === 'folder' ? '📁' : '📄'} {node.name}
        {expanded && node.children?.map(child => renderNode(child, depth + 1, currentPath))}
      </div>
    );
  };

  return <div>{tree.map((node) => renderNode(node, 0, ''))}</div>;
}
