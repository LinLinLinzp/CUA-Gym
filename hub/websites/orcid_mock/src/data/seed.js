export function createInitialData() {
  return {
    researcher: { name: 'Alex Morgan', defaultVisibility: 'Everyone' },
    works: [
      { id: 'work-001', title: 'Mapping coastal change with historical imagery', type: 'Journal article', year: '2024', source: 'Alex Morgan', sourceKind: 'self', visibility: 'Everyone' },
      { id: 'work-002', title: 'Open data for shoreline monitoring', type: 'Dataset', year: '2023', source: 'Coastal Research Archive', sourceKind: 'organization', visibility: 'Everyone' }
    ]
  }
}
