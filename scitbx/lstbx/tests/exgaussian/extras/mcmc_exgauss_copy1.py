from __future__ import division
from scitbx.array_family import flex
from scitbx import sparse
from scitbx.lstbx import normal_eqns, normal_eqns_solving
from libtbx.test_utils import approx_equal, Exception_expected
import math
import numpy as np
from test3_logarithm import mcmc

class exgauss_fit(
  normal_eqns.non_linear_ls,
  normal_eqns.non_linear_ls_mixin):

  """ See Sharma/Neutze (2017) Acta. D
      Fitting an exgaussian distribution to
      intensity data (CDF) derived from XFEL experiments
      The final output of minimization should be [mu,sigma,tau]
      Please see wikipedia/below for CDF form of an exgaussian
  """


  def __init__(self, datasource):
    super(exgauss_fit, self).__init__(n_parameters=3)
    # 2 cases to be considered here
    # a. datasource is a filename
    # b. datasource is an flex array or a list or a numpy array
    self.t, self.y = self.read_data(datasource) #0.02*flex.double_range(1, self.n_data + 1)
    self.x_0 = self.initial_guess()
    assert len(self.y) == len(self.t)
    self.n_data = len(self.t)
    self.restart()

  def restart(self):
    self.x = self.x_0.deep_copy()
    self.old_x = None

  def read_data(self, datasource):
    exgauss = True
    is_fake_exgauss = False
    # Ex-Gaussian Data
    if (exgauss):
      if (not is_fake_exgauss):
        t = []
        y = []
        fin = open(filename,'r')
        miller_index = '0_0_0'
        for line in fin:
          if '#' in line:
            ax = line.split()
            miller_index = '%s_%s_%s'%(ax[-3],ax[-2],ax[-1])
          else:
            ax = line.split()
            if float(ax[0]) > -1.e15 and float(ax[0]) < 1.e15:
              t.append(float(ax[0]))
        fin.close()
      else:
        fake_data_params = [-1000.0, 5000.0, 5000.0]
        t = range(-20000, 20000, 10)
        y = self.exgauss_cdf_array(t, fake_data_params[0], fake_data_params[1], fake_data_params[2])

    # Gaussian Data
    else:
      raise Exception('Data Fitting should be to an Exgaussian, Sorry !')

    # Adjust CDF to make it (n-0.5)/N instead of n/N to create a buffer
    if (not is_fake_exgauss):
      t = np.sort(t)
      y = np.array(range(1,len(t)+1))/float(len(t))
      y[:] = [z-0.5/len(y) for z in y]

    t = flex.double(t)
    y = flex.double(y)
    return [t,y] 

  ## FIXME ####
  def initial_guess(self):
    data = self.t.as_numpy_array()
    wiki = False
    gamma = (np.mean(data)-np.median(data))/np.std(data)
    if (wiki):
      m = np.mean(data)
      s = np.std(data)
      mu = m-s*((gamma/2.)**(1./3))
      sigma = np.sqrt(s*s*(1-((gamma/2.)**(2./3))))
      tau = s*((gamma/2.)**1./3)
    else:
      mu = np.mean(data) - gamma #skewness(data)
      tau = np.std(data)*0.8
      sigma = np.sqrt(np.var(data)-tau*tau)
#    return flex.double([-1.250959e+05, 5.06495e+02, 9.31455e+05])
    return flex.double([mu,sigma,tau])


  def gauss_cdf(self,x,mu,sigma):
    return 0.5*(1+math.erf((x-mu)/(math.sqrt(2)*sigma)))

  def exgauss_cdf_array(self,data,mu,sigma,tau):
    cdf = []
    for x in data:
      u = (x-mu)/tau
      v = sigma/tau
      if self.gauss_cdf(u,v*v,v) == 0.0:
        cdf.append(self.gauss_cdf(u,0,v))
      else:
        cdf.append(self.gauss_cdf(u,0,v)-np.exp(-u+0.5*v*v)*(self.gauss_cdf(u,v*v,v)))
    return flex.double(cdf)

  def exgauss_cdf(self,x, mu, sigma, tau):
    u = (x-mu)/tau
    v = sigma/tau
#    print u,v,self.gauss_cdf(u,0,v), self.gauss_cdf(u,v*v,v)
    return self.gauss_cdf(u,0,v)-np.exp(-u+0.5*v*v)*(self.gauss_cdf(u,v*v,v))

  def get_residual_grad(self, mu, sigma, tau):
    import numpy as np
    result = 0.0
    mu_grad = []
    sigma_grad = []
    tau_grad = []
    prefactor = 1.0
    for i in range(0, self.t.size()):
      y_calc = self.exgauss_cdf(self.t[i], mu, sigma, tau)
      u = (self.t[i]-mu)/tau
      v = sigma/tau
      phi_uv2v = self.gauss_cdf(u, v*v, v)
      z1 = (self.t[i] - mu)/(sigma*np.sqrt(2))
      z2 = (self.t[i]- mu-(sigma*sigma/tau))/(sigma*np.sqrt(2))
      exp_1 = np.exp(-z1*z1)/np.sqrt(2*np.pi*sigma*sigma)
      exp_2 = np.exp(-z2*z2)/np.sqrt(np.pi)
      exp_0 = np.exp(-u+0.5*v*v)

      mu_grad.append(prefactor*((-exp_1) - exp_0*((phi_uv2v/tau) + (exp_2*(-1./(sigma*np.sqrt(2)))))))
      sigma_grad.append(prefactor*((-exp_1*z1*np.sqrt(2)) - exp_0*((phi_uv2v*sigma/(tau*tau))+(exp_2*(-np.sqrt(2)/tau - z2/sigma)))))
      tau_grad.append(prefactor*((0.0) - exp_0*((phi_uv2v*u/tau) - (phi_uv2v*v*v/tau) + (exp_2*(v/(tau*np.sqrt(2)))))))

    return [flex.double(mu_grad), flex.double(sigma_grad), flex.double(tau_grad)]



  def parameter_vector_norm(self):
    return self.x.norm()

  def build_up(self, objective_only=False):
    mu, sigma, tau = self.x
    residuals = self.exgauss_cdf_array(self.t, mu, sigma, tau)
    residuals -= self.y

    self.reset()
    if objective_only:
      self.add_residuals(residuals, weights=None)
    else:
      grad = self.get_residual_grad(mu, sigma, tau) 
      grad_r = (grad[0],
                grad[1],
                grad[2])
      jacobian = flex.double(flex.grid(self.n_data, self.n_parameters))
      for j, der_r in enumerate(grad_r):
        jacobian.matrix_paste_column_in_place(der_r, j)
      self.add_equations(residuals, jacobian, weights=None)

  def step_forward(self):
    self.old_x = self.x.deep_copy()
    self.x += self.step()

  def step_backward(self):
    assert self.old_x is not None
    self.x, self.old_x = self.old_x, None

def exercise_levenberg_marquardt(non_linear_ls):
  non_linear_ls.restart()
  iterations = normal_eqns_solving.levenberg_marquardt_iterations(
    non_linear_ls,
    track_all=True,
    gradient_threshold=1e-12,
    step_threshold=1e-12,
    tau=1e-8,
    n_max_iterations=200)
  print "L-M: %i iterations" % iterations.n_iterations

class mcmc_exgauss():
  def __init__(self, filename, cdf_cutoff=0.95, nsteps = 50000, t_start=40000, dt = 10000, mcmc_seed = 22, plot=False):
    self.filename = filename
    self.cdf_cutoff = cdf_cutoff
    self.nsteps = nsteps
    self.t_start = t_start
    self.dt = dt
    self.mcmc_seed = mcmc_seed
    self.plot = plot

  def run(self):
    import matplotlib.pyplot as plt
    print '--------------------- Minimization ----------------------------------'
    intensities = exgauss_fit(self.filename)
    exercise_levenberg_marquardt(intensities)
    initial = intensities.x_0
    mu0,sigma0,tau0 = intensities.x
    print 'OK'
    print 'Initial Values of params   = %10.4f, %10.4f, %10.4f'%(initial[0], initial[1], initial[2])
    print 'Final Values of parameters = %10.4f, %10.4f, %10.4f\n'%(mu0,sigma0,tau0)
    X1 = intensities.t.as_numpy_array()
    Y1 = intensities.y.as_numpy_array()
    from construct_random_datapt import ExGauss
    EXG= ExGauss(10000, np.min(X1), np.max(X1), mu0, sigma0, tau0)
    I_fit0 = EXG.interpolate_x_value(self.cdf_cutoff)
    print 'Initial I_%.2f value = '%self.cdf_cutoff, I_fit0
    plt.figure(1)
    plt.plot(X1,Y1,'.')
    if (1):
      F0 = intensities.exgauss_cdf_array(X1, initial[0], initial[1], initial[2])
      F1 = intensities.exgauss_cdf_array(X1,mu0, sigma0, tau0)
      F2 = intensities.exgauss_cdf_array(X1,-4000.0,4000.0, 25000.0)
    print 'Sum Squared Difference = ',sum(map(lambda x:x*x,F1-Y1))
    plt.plot(X1, F0, 'r*', linewidth=2.0)
    plt.plot(X1,F1,'g+',linewidth=2)
    plt.ylabel('CDF value')
    plt.xlabel('Intensities')
    # Plot difference between obs and calc values
    plt.figure(2)
    plt.plot(X1, (F1-Y1), 'o')
    plt.ylabel('$\Delta(CDF_{calc}-CDF_{obs})$', fontsize=18)
    plt.xlabel('Intensities', fontsize=18)

# Now do the MCMC stuff
    print '======================= MCMC stuff beginning ============================'
#    nsteps = 5
#    t_start = 5
#    dt = 1000
    maxI = np.max(X1)+np.max(X1)/5.
    minI = np.min(X1)-np.min(X1)/5.
    proposal_width =  0.01*np.abs(maxI-minI)
    print 'initial guesses and proposal width = ',mu0, sigma0, tau0, proposal_width
    mcmc_helper = mcmc()
    params = mcmc_helper.sampler(X1, samples=self.nsteps, mu_init= mu0,sigma_init = sigma0, tau_init = tau0,
                   proposal_width = proposal_width,plot=False, seed=self.mcmc_seed)
    mu,sigma, tau = params[-1]
    print 'final parameter values ',mu,sigma, tau
    plt.figure(3)
    plt.plot(X1, F1, 'green')
    F1 = intensities.exgauss_cdf_array(X1, mu,sigma,tau)
    plt.plot(X1,F1,'grey')
    I_mcmc = []
#  fout = open('params_mcmc_%s.dat'%seed, 'a')
#  for count in range(t_start,nsteps):
#    fout.write("%14.6f   %14.6f  %14.6f\n" %(params[count][0],params[count][1], params[count][2]))
#  fout.close()
#  exit()
    for count in range(self.t_start, self.nsteps,self.dt):
      mu,sigma, tau = params[count]
      EXG= ExGauss(10000, minI, maxI, mu,sigma,tau)
      I_mcmc.append(EXG.interpolate_x_value(self.cdf_cutoff))
# Get CDFs
#    F1 = exgauss_cdf(X1,mu,sigma,tau)
#    plt.plot(X1,F1,'grey',linewidth=1.0)
#  print 'Mean and Stdev of I_mcmc = %12.7f, %12.7f'%(np.mean(I_mcmc), np.std(I_mcmc))
    import os
    seed = os.path.split(self.filename)[-1].split('.')[0].split('_')[-1]
#    fout = open('intensity_mcmc_%s.dat'%seed, 'a')
    fout = open('intensity_mcmc_%.2f.dat'%self.cdf_cutoff, 'a')
    fout.write('Mean and Stdev of I_mcmc = %12.7f, %12.7f in file %s %d\n'%(np.mean(I_mcmc), np.std(I_mcmc), self.filename,self.mcmc_seed))
    fout.close()
#  X2 = np.sort(x_obs)
#  F2 = np.array(range(len(x_obs)))/float(len(x_obs))
#  plt.plot(X2,F2,'o')
    if self.plot:
      plt.show()

if __name__ == '__main__':
  import sys
  mcmc_test = mcmc_exgauss(filename=sys.argv[1], cdf_cutoff=0.95, nsteps=10, t_start=1, dt=1, plot=True)
  mcmc_test.run()
