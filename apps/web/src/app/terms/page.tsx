import type { Metadata } from 'next';
import Link from 'next/link';
import { legalConfig, legalConfigIsComplete } from '@/lib/legal-config';

export const metadata: Metadata = {
  title: 'Termos de Uso',
  description: 'As regras de uso do Noema.',
  alternates: { canonical: '/terms' },
};

export default function TermsPage() {
  const complete = legalConfigIsComplete();

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Link href="/" className="font-display text-lg tracking-tight text-ink-900">
          NOEMA
        </Link>
      </header>

      <article className="prose-reading mx-auto px-6 pb-24 pt-8">
        <h1 className="font-display text-3xl text-ink-900">Termos de Uso</h1>
        <p className="mt-2 text-sm text-ink-500">Última atualização: a definir no lançamento.</p>

        {!complete && (
          <div className="my-8 rounded-md border border-critical/40 bg-critical/5 p-4">
            <p className="text-sm font-medium text-critical">
              Configuração necessária antes do lançamento
            </p>
            <p className="mt-1 text-sm text-ink-700">
              A razão social, o endereço e o email de contato do Noema ainda não foram
              preenchidos (<code>apps/web/src/lib/legal-config.ts</code>). Esta página não
              deve ser publicada como definitiva até que estejam.
            </p>
          </div>
        )}

        <h2>O que é o Noema</h2>
        <p>
          O Noema é uma ferramenta de estudo e aprendizado com apoio de inteligência
          artificial. Ele ajuda você a organizar material, entender conceitos, praticar e
          revisar o que aprendeu.
        </p>
        <p>
          <strong>O Noema não é</strong> uma instituição de ensino credenciada e não oferece
          certificação profissional, diploma, habilitação ou licença de qualquer tipo. Nada no
          produto substitui um curso formal, uma licença profissional ou aconselhamento
          especializado (médico, jurídico, financeiro) quando isso for necessário.
        </p>

        <h2>Sua conta</h2>
        <p>
          Você é responsável por manter suas credenciais em segurança. Contas são pessoais e
          não podem ser compartilhadas. Você pode encerrar sua conta a qualquer momento nas
          configurações; isso cancela qualquer assinatura ativa.
        </p>

        <h2>Assinaturas e cobrança</h2>
        <p>
          Planos pagos são cobrados de forma recorrente, processados pela Stripe. Você pode
          cancelar a qualquer momento; o acesso ao plano pago continua até o fim do período já
          pago. Não fazemos reembolso de períodos parciais já utilizados, salvo exigência
          legal.
        </p>

        <h2>Uso aceitável</h2>
        <p>
          Não use o Noema para gerar, armazenar ou distribuir conteúdo ilegal, para tentar
          contornar os limites de uso da IA, ou para qualquer atividade que viole direitos de
          terceiros. Contas usadas de forma abusiva podem ser suspensas.
        </p>

        <h2>Conteúdo que você envia</h2>
        <p>
          O material que você envia (notas, documentos, perguntas) continua seu. Você garante
          que tem o direito de enviá-lo e de usá-lo com uma ferramenta de IA. O Noema usa esse
          conteúdo apenas para operar o produto para você — para gerar explicações, flashcards,
          questões e acompanhar seu progresso.
        </p>

        <h2>Sem garantias</h2>
        <p>
          O Noema é fornecido &ldquo;como está&rdquo;. Respostas geradas por IA podem conter erros —
          verifique informações importantes antes de confiar nelas para decisões críticas. Não
          garantimos disponibilidade ininterrupta do serviço.
        </p>

        <h2>Contato</h2>
        <p>
          Dúvidas sobre estes termos:{' '}
          {legalConfig.contactEmail ? (
            <a href={`mailto:${legalConfig.contactEmail}`} className="text-accent">
              {legalConfig.contactEmail}
            </a>
          ) : (
            '[email de contato a definir]'
          )}
          .
        </p>
      </article>
    </main>
  );
}
