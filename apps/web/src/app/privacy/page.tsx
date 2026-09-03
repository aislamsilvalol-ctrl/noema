import type { Metadata } from 'next';
import Link from 'next/link';
import { legalConfig, legalConfigIsComplete } from '@/lib/legal-config';

export const metadata: Metadata = {
  title: 'Política de Privacidade',
  description: 'O que o Noema coleta, por que, e para onde vai.',
  alternates: { canonical: '/privacy' },
};

/**
 * Real, product-specific content -- what this codebase actually does, not a
 * generic template. Written once, in Portuguese only: this session's own
 * pricing (BRL) and the brief that asked for this page both point at Brazil
 * as the real jurisdiction, and a machine-translated legal document in three
 * languages risks being wrong in ways a missing translation isn't. Company
 * identity comes from `legalConfig`, deliberately `null` until a real value
 * is filled in -- see that file's own docstring for why nothing here
 * invents one.
 */
export default function PrivacyPage() {
  const complete = legalConfigIsComplete();

  return (
    <main className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Link href="/" className="font-display text-lg tracking-tight text-ink-900">
          NOEMA
        </Link>
      </header>

      <article className="prose-reading mx-auto px-6 pb-24 pt-8">
        <h1 className="font-display text-3xl text-ink-900">Política de Privacidade</h1>
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

        <h2>Quem somos</h2>
        <p>
          {legalConfig.companyName ?? '[razão social a definir]'}, operando o Noema
          {legalConfig.address ? (
            <>
              , com sede em {legalConfig.address}
              {legalConfig.city ? `, ${legalConfig.city}` : ''}
              {legalConfig.region ? ` - ${legalConfig.region}` : ''}
              {legalConfig.postalCode ? `, ${legalConfig.postalCode}` : ''}
              {legalConfig.country ? `, ${legalConfig.country}` : ''}
            </>
          ) : (
            ' [endereço a definir]'
          )}
          .
        </p>

        <h2>O que coletamos</h2>
        <p>
          <strong>Conta:</strong> email, senha (armazenada como hash, nunca em texto puro) e
          nome de exibição.
        </p>
        <p>
          <strong>Conteúdo de aprendizado:</strong> os notebooks, notas, fontes que você envia
          (PDF, DOCX, Markdown, texto, CSV, URLs, transcrições), flashcards, perguntas e
          respostas, histórico de revisão e o estado de domínio estimado por conceito.
        </p>
        <p>
          <strong>Conversas com a IA:</strong> as mensagens trocadas com o Noema (Professor,
          modo Socrático, explicações) são enviadas ao provedor de IA configurado para gerar
          uma resposta. Se você configurar sua própria chave de API (BYOK), a conversa é
          enviada usando essa chave, diretamente ao provedor escolhido.
        </p>
        <p>
          <strong>Cobrança:</strong> pagamentos são processados pela Stripe. O Noema não
          armazena dados de cartão de crédito diretamente.
        </p>
        <p>
          <strong>Cookies:</strong> apenas cookies essenciais de sessão e proteção CSRF,
          necessários para manter você autenticado. O Noema não usa cookies de rastreamento
          publicitário.
        </p>
        <p>
          <strong>Analytics:</strong> usamos o Plausible, uma ferramenta de métricas que não
          usa cookies e não coleta dados pessoais identificáveis — apenas contagens agregadas
          de visitas e eventos de uso do site.
        </p>

        <h2>Para onde seus dados vão</h2>
        <p>
          Suas conversas e, quando relevante para responder sua pergunta, trechos do seu
          próprio material são enviados ao provedor de IA configurado para esta conta
          (Anthropic e/ou OpenAI, dependendo da configuração) para gerar uma resposta. Isso é
          necessário para o Noema funcionar — não é uma afirmação de que &ldquo;nada sai dos
          nossos servidores&rdquo;, porque isso não seria verdade.
        </p>
        <p>
          Arquivos que você envia são armazenados de forma privada, associados apenas à sua
          conta, e nunca ficam acessíveis a outros usuários.
        </p>

        <h2>Exclusão de conta</h2>
        <p>
          Você pode excluir sua conta a qualquer momento. Isso cancela qualquer assinatura
          ativa e agenda a remoção permanente dos seus dados após um período de carência.
        </p>

        <h2>Contato</h2>
        <p>
          Dúvidas sobre esta política:{' '}
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
