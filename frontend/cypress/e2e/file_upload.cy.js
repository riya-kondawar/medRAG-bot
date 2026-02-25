describe('File Upload UI Test', () => {
  it('uploads a PDF and displays results', () => {
    cy.visit('/');
    cy.get('input[type="file"]').attachFile('Report1.pdf');
    cy.contains('Uploading').should('exist');
    cy.contains('Analysis').should('exist');
    cy.contains('Lymphocytes').should('exist');
    cy.contains('MPV (Mean Platelet Volume)').should('exist');
    cy.contains('Absolute Lymphocyte Count').should('exist');
  });
});