export function createInitialData() {
  return {
    titles: [
      { id: 'botany-2025', title: 'Botany', author: 'Kratz, René Fester', format: 'Book', edition: '2nd edition', year: '2025', callNumber: '580 K867b', availability: 'Available', canHold: true, cover: 'botany.jpg' },
      { id: 'botany-kovacs', title: 'Botany', author: 'Kovacs, Charles', format: 'eBook', year: '2020', callNumber: 'EBOOK HOOPLA', availability: 'Instantly available on hoopla', canHold: false, cover: 'botany-kovacs.jpg' },
      { id: 'botany-1876', title: 'Botany', author: 'Geological Survey of California', format: 'Book', year: '1876–80', callNumber: '581.9794 C12', availability: 'In-library use only', canHold: false }
    ],
    branches: [{ id: 'main', name: 'Main Library' }, { id: 'richmond', name: 'Richmond' }, { id: 'sunset', name: 'Sunset' }],
    holds: [],
    forLater: [],
    checkouts: [
      { id: 'loan-01', title: 'Braiding Sweetgrass', author: 'Kimmerer, Robin Wall', format: 'Book', dueDate: '2026-11-25', renewalDates: ['2026-12-16'], renewals: 0 },
      { id: 'loan-02', title: 'The Hidden Life of Trees', author: 'Wohlleben, Peter', format: 'Book', dueDate: '2026-11-23', renewalDates: [], renewalBlock: 'Another patron has requested this title.', renewals: 0 }
    ]
  }
}
